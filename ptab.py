#!/usr/bin/env python3

import requests
import json
import os.path
import sys
import re
import subprocess
import agg
import datetime
import time
import csvplus

DECISION_FILE = 'ptab.json'
PDF_FOLDER = 'decisions/pdf'
TEXT_FOLDER = 'decisions/text'
CAFC_FILE = 'cafc.csv'

API_URL_PREFIX = 'https://developer.uspto.gov/ptab-api/'

def get_decisions(batch_size = 500):
    total = batch_size
    start = 0
    records = []
    while start < total:
        print(f"Batch {start}, total {total}")
        r = requests.get(API_URL_PREFIX + 'decisions',
                params = { 'proceedingTypeCategory': 'AIA Trial',
                    'recordStartNumber': start,
                    'recordTotalQuantity': batch_size },
                headers = { 'Accept': 'application/json' })
        data = r.json()
        if 'results' in data: records.extend(data['results'])
        total = data['recordTotalQuantity']
        start += batch_size

    return records

def save_decisions():
    with open(DECISION_FILE, 'w') as io:
        decisions = get_decisions()
        json.dump(decisions, io)

def document_filename(decision_record, fmt = 'pdf', directory = True):
    """The filename to be given for a decision"""
    format_info = {
        'pdf': ('.pdf', PDF_FOLDER),
        'txt': ('.txt', TEXT_FOLDER),
        'text': ('.txt', TEXT_FOLDER),
    }[fmt]
    di = decision_record['documentIdentifier']
    filename = di + format_info[0]
    if not directory: return filename
    return os.path.join(format_info[1], filename)


def check_decisions_for_text(decisions, fix = True):
    """
        Given a list of decisions, checks that each of them has a text file.
        Raises an error if a file is missing.
    """
    errs = []
    for d in decisions:
        file = document_filename(d, fmt = 'txt')
        if not os.path.exists(file):
            errs.append(d)
    if len(errs) > 0:
        if fix:
            for d in errs:
                download_document(d)
            convert_to_text(
                document_filename(d, "pdf", directory = False) for d in errs
            )
        else:
            errs = [ document_filename(d, fmt = 'txt') for d in errs ]
            raise AssertionError(f"Missing files {errs}")

def download_document(decision_record):
    """
        Downloads the PDF document associated with a decision.
    """

    filename = document_filename(decision_record)
    if os.path.exists(filename): return

    r = requests.get(decision_url(decision_record))
    with open(filename, 'wb') as io:
        io.write(r.content)
    return filename

def decision_url(decision_record):
    """
        Returns the URL for a PTAB decision.
    """
    return API_URL_PREFIX + 'documents/' \
            + str(decision_record['documentIdentifier']) + '/download'

the_decisions = None
def decisions():
    """ Reads the file of decisions"""
    global the_decisions
    if the_decisions is None:
        with open(DECISION_FILE) as io:
            the_decisions = agg.Table(select_decisions(json.load(io)))
            cafc = cafc_decisions()

            # Add info to the decisions table
            for d in the_decisions:
                d['outcome'] = interpret_orders(d)
                d['appeals'] = cafc.get('orig_docket', d['proceedingNumber'])

            # Index values
            the_decisions.index(
                'patent_no',
                lambda row: row.get('respondentPatentNumber', None)
            )
            the_decisions.index(
                'docid',
                lambda row: row.get('documentIdentifier', None)
            )
            the_decisions.index('outcome', lambda row: row['outcome'])
            the_decisions.index('proc', lambda row: row['proceedingNumber'])

    return the_decisions

def select_decisions(all_decisions):
    """
        Selects decisions of interest (not rehearings or duplicative older
        decisions).
    """
    res = []
    index = {}
    for dec in all_decisions:
        if dec['decisionTypeCategory'] != 'Decision': continue
        if dec['ocrSearchText'].startswith('BLANK\n'): continue

        procno = dec['proceedingNumber']
        if procno in index:
            existing_dec = res[index[procno]]
            if int(dec['documentIdentifier']) \
                > int(existing_dec['documentIdentifier']):
                res[index[procno]] = dec
        else:
            index[procno] = len(res)
            res.append(dec)
    return res

the_cafc_decisions = None
def cafc_decisions():
    """
        Read the Federal Circuit decisions and sort them by docket below.
    """
    global the_cafc_decisions
    if the_cafc_decisions is not None: return the_cafc_decisions
    with open(CAFC_FILE, newline = '') as io:
        reader = csvplus.Reader(io, dialect = 'excel')
        reader.header_proc = lambda x: x.lower()
        res = agg.Table([])
        for row in reader:
            if row['uniqueid'] == '15623':
                row['orig_trib_dockets'] = 'IPR2014-00549;IPR2014-00550;'\
                        'IPR2015-00265;IPR2015-00268'
            if row['uniqueid'] == '15473':
                row['orig_trib_dockets'] = 'IPR2014-00325'

            if row['orig_trib_dockets'] == '': continue
            split_cafc_dockets(row, 'orig_trib_dockets')
            split_cafc_dockets(row, 'appeal_dockets')
            row['print_name'] = \
                    row['full_cite'] if row['full_cite'] != '' \
                    else f"{row['appeal_dockets'][0]}"
            res.append(row)
        res.index_multi('orig_docket', lambda r: r['orig_trib_dockets'])
        res.index('id', lambda r: r['uniqueid'])
        the_cafc_decisions = res
        return res

def split_cafc_dockets(row, header):
    """
        Splits a row containing docket numbers, and cleans them up.
    """
    d = [
        cn
        for n in row[header].upper().replace(' ', '').split(";")
        for cn in clean_docket_no(n)
    ]
    row[header] = d

def clean_docket_no(num):
    """
        Cleans up a docket number
    """
    num = re.sub(r"\.$", "", num)
    num = re.sub(r"^CMB", "CBM", num)
    num = re.sub("^PR", "IPR", num)
    ipr_re = r"(?:IPR|PGR|CBM)\d\d\d\d-\d\d\d\d\d"
    app_re = r"\d\d/\d\d\d,\d\d\d"
    cv_re = r"\d:\d\d-CV-\d\d\d\d\d"
    if re.fullmatch(ipr_re, num):
        # IPR/PGR/CBM
        return [ num ]
    elif re.fullmatch(cv_re, num):
        # District court docket. This comes up once due to a consolidated case.
        # Note that this suggests a larger problem that if a case originates
        # from two tribunals (district court and PTAB here), then the database
        # fields are insufficient to characterize the case.
        return [ ]
    elif re.fullmatch(app_re, num):
        # Appeals by patent application numbers
        return [ num ]
    elif re.fullmatch(r"\d\d\d\d-\d\d\d\d\d", num):
        # Federal Circuit dockets
        return [ num ]
    elif re.fullmatch(r"\d\d\d\d\d\d", num):
        # PTAB docket numbers
        return [ num ]
    elif re.fullmatch(r"\d\d\d\d\d\d\d\d", num):
        # TTAB docket numbers--not sure why my search got them
        return [ num ]
    elif (m := re.fullmatch(f"({ipr_re}),({ipr_re})", num)):
        # IPR docket numbers joined by a comma
        return [ m[1], m[2] ]
    elif (m := re.match(ipr_re, num)):
        # There is one IPR docket number with extra text appended
        return [ m[0] ]
    elif (m := re.fullmatch(r"(IPR\d\d\d\d)0(\d\d\d\d\d)", num)):
        # There is one IPR docket number with a zero rather than a dash
        return [ m[0] ]
    elif (m := re.fullmatch(f"({app_re}),({app_re})", num)):
        # Application numbers joined by a comma
        return [ m[1], m[2] ]
    elif (m := re.fullmatch(r"(IPR\d\d\d\d-)(\d+)", num)):
        # IPR numbers with the second part having the wrong number of digits
        return [ f"{m[1]}{int(m[2]):05}" ]
    elif re.fullmatch(r"IPR\d\d\d\d-", num):
        # IPR numbers missing the second part. These appear to occur when the
        # Federal Circuit opinion breaks a line across the docket number. For my
        # purposes, none of the cases are of interest.
        return [ ]
    elif num == 'CBM00160':
        # Just fixing this one manually
        return [ 'CBM2015-00160' ]
    elif num == '':
        return []
    else:
        print(f"Unparseable {num}", file = sys.stderr)
        return [num]

def decisions_with_files():
    """Selects those decisions that have files."""
    files = { f.replace(".pdf", "") for f in os.listdir(PDF_FOLDER) }
    return [ d for d in decisions() if d['documentIdentifier'] in files ]

def decisions_for_patents(patents):
    return decisions().get_multi('patent_no', patents)

def convert_to_text(files = None):
    """Converts all the PDF decisions to text."""
    if files is None: files = os.listdir(PDF_FOLDER)
    for pdf in files:
        text = os.path.join(TEXT_FOLDER, pdf.replace(".pdf", ".txt"))
        subprocess.run([
            "pdftotext", "-layout", os.path.join(PDF_FOLDER, pdf), text
        ])

order_re = r"^\s*(?:[\w]+\.\s+)?(CONCLUSION|Conclusion|ORDER|Order)$"
ordered_re = r"\bORDERE?D(?: that|,|:)*(?:\s+|$)|it is hereby ordered that "
patent_re = r"(?:Patent |US )?(?:RE)?[\d, BE]+"
ipr_re = (
    r"^\f?(?:"
    r"(?:Case )?(?:IPR|PGR)\d+-\d+"
    r"(?: \(?" + patent_re + r"\)?)?"
    r"(?:;\s+)?"
    r")+$"
)
def decision_orders(decision_record, filtered = False):
    """
        Given a decision record, reads the text file of the decision and
        extracts all the orders. If filtered = True, then runs filter_orders()
        on the result.
    """
    orders = []
    appending = False
    footnote = False
    filename = document_filename(decision_record, "txt")
    if not os.path.exists(filename): return ('no file',)

    with open(filename) as io:
        for line in io:
            if "\f" in line: footnote = False
            if orders is None:
                if re.match(order_re, line): orders = []
            elif m := re.search(ordered_re, line):
                orders.append(line[m.end():].strip())
                appending = True
            elif line == "\n":
                pass
            elif re.match(r"^\d+$", line):
                footnote = True
            elif re.match(ipr_re, line):
                footnote = False
                pass
            elif re.match(r"^\s+\d+$", line):
                footnote = False
                pass
            elif re.match(f"^{patent_re}$", line):
                footnote = False
                pass
            elif "PETITIONER" in line or "For Petitioner" in line:
                appending = False
            elif re.match(r"^Petitioner:$", line):
                appending = False
            elif "UNITED STATES PATENT AND TRADEMARK OFFICE" in line:
                appending = False
            elif appending and not footnote and len(orders) > 0:
                if re.match("^\s+\d+\. ", line):
                    # Some orders are in enumerated lists
                    orders.append(line.strip())
                else:
                    orders[-1] += " " + line.strip()
    if filtered:
        return filter_orders(orders)
    else:
        return orders


claims_re = r"[cC]laims? (?:[\d, –−‒-]| and )+(?= (?:of|are|have|by)\b)"
poe_re = r"(?:(?:,? |^)by a preponderance of the evidence,?)?"


#
# Table of regular expressions for determining disposition of outcomes.
#
order_filters = (
    (   # [claims] are not held unpatentable
        re.compile(
            claims_re + r".*\b(?:"
            r"(?:has|have) not be(?:en)? (?:shown|prove[dn])" + poe_re
            + " (?:to be )?unpatentable"
            r"|(?:is|are) not (?:held|determined|shown) (?:to be )?unpatentable"
            r"|(?:is|are) (?:held|determined|shown) (?:to be )?not unpatentable"
            r"|(?:is|are) not unpatentable"
            r")\b",
            re.IGNORECASE
        ),
        "not unpatentable"
    ),
    (   # Petitioners have not shown [claims] unpatentable
        re.compile(
            r"Petitioners? (?:has |have |do(?:es)? )?"
            r"(?:not(?: been)?|failed(?: to)?) "
            r"(?:shown?|prove[nd]?|demonstrated?|establishe?[sd]?)"
            + poe_re
            + r" (?:that )?" + claims_re + ".*(?:is|are) unpatent?able",
            re.IGNORECASE
        ),
        "not unpatentable",
    ),
    (   # Petitioners have not shown the unpatentability of [claims]
        re.compile(
            r"Petitioners? (?:has |have )?"
            r"(?:not(?: be(?:en)?)?|failed to) "
            r"(?:shown?|prove[nd]?|demonstrated?)"
            + poe_re
            + r" the unpatentability of " + claims_re
        ),
        "not unpatentable",
    ),
    (   # [claims] are held unpatentable
        re.compile(
            claims_re + r".*\b(?:"
            r"(?:has|have) been (?:shown|prove[dn])"
            + poe_re + " to be unpatentable"
            r"|(?:is|are) held (?:to be )?unpatentable"
            r"|(?:is|are|be) cancell?ed"
            r")\b"
            , flags = re.IGNORECASE
        ),
        "unpatentable"
    ),
    (   # [Petitioners have proved that] [claims] are unpatentable
        re.compile(
            r"^(?:"
            r"Petitioners? (?:has |have )?"
            r"(?:show[sn]?|prove[snd]?|demonstrate[ds]?|establish(?:ed|es)?))?"
            + poe_re
            + r"(?: that)? ?"
            + claims_re
            + ".*are (?:determined to be )?unpatentable"
        ),
        "unpatentable"
    ),
    (
        # Patent owner request for adverse judgment
        re.compile(
            r"Patent Owner.* request for adverse judgment.*is granted"
            r"|adverse judgment is entered.*against patent owner"
            , flags = re.IGNORECASE
        ),
        "unpatentable"
    ),
    (   # Terminations and adverse judgments
        re.compile(
            r"(?:motion|request)s? .*to terminate .* granted"
            r"|adverse judgment is entered against Petitioner"
            r"|(?:proceeding|review)s? .*(?:is|are)(?: hereby)? terminated"
            r"|case .* is hereby terminated"
            r"|motion to dismiss the petition is granted"
            , flags = re.IGNORECASE
        ),
        "terminated"
    ),
    (   # Non-institution
        re.compile(
            r"no inter partes review is instituted"
            r"|no trial is instituted"
            r"|the petition is denied a[ts] to all challenged claims"
            r"|(?:petition|request) for (?:an )?inter partes review "
            r".* is denied\."
            , flags = re.IGNORECASE
        ),
        "not instituted"
    ),
    (   # Motion dispositions
        re.compile(
            r"motions? (?:to|for) (?:"
            r"exclude|amend|seal|(?:submit|file) supplemental information"
            r"|entry of (?:a |stipulated )*protective order"
            r"|strike|joinder|keep confidential"
            r") ",
            flags = re.IGNORECASE
        ),
        None
    ),
    (   # Other inconsequential orders
        re.compile(
            r"the settlement agreement.*be (?:treated|made available)"
            r"|business confidential"
            r"|the parties shall file.*a redacted version"
            r"|shall refile revised redacted versions"
            r"|shall file its proposed public version"
            r"|this constitutes a final written decision"
            r"|because this is a Final Written Decision"
            r"|part(?:ies|y) to th(?:e|is) proceeding seeking judicial review"
            r"|Protective Order"
            r"|Requests? to Strike"
            r"|(?:shall be|are) expunged from (?:the )?record"
            r"|shall be unsealed"
            r"|a certificate shall issue"
            r"|(Exhibit|paper)s? .* (?:is|are|be) expunged"
            r"|^$"
            r"|(?:requests? for rehearing|rehearing requests?)"
            r"|(?:is|are) joined as Petitioners?"
            r"|scheduling order|cross-examination|discovery"
            , flags = re.IGNORECASE
        ),
        None
    ),
    (re.compile(r""), "unknown"),
)

def filter_orders(orders, which = None, keep = False):
    """
        For each order in orders, translates into a keyword describing the
        order. The module variable order_filters identifies the relevant tests.
        Returns the set of unique keywords found.

        If which is set to a number, then only runs the test in that item of
        order_filters, returning a list of matching orders. This is useful for
        testing whether an order_filters test is being over- or underinclusive.

        If keep = True, then returns a dict mapping order texts to keywords.
        This is useful for testing if orders are being mapped correctly.
    """
    if which is None:
        if keep:
            res = {}
        else:
            res = set()
        for order in orders:
            for pattern, action in order_filters:
                if pattern.search(order):
                    if action is not None:
                        if keep: res[order] = action
                        else: res.add(action)
                    break
        return res
    else:
        ore = order_filters[which][0]
        return [ o for o in orders if ore.search(o) ]

def interpret_orders(decision):
    """
        Converts the orders for a decision into a single string.
    """
    orders = decision_orders(decision, True)
    if 'not unpatentable' in orders and 'unpatentable' in orders:
        return 'mixed'
    elif 'unpatentable' in orders:
        return 'unpatentable'
    else:
        return 'not unpatentable'


def patent_outcome(patent):
    """
        Given one patent, determines its PTAB outcome and returns it as a single
        string.
    """
    decs = { dec['outcome'] for dec in decisions().get('patent_no', patent) }
    if len(decs) == 0: return "unlitigated"
    if 'unpatentable' in decs: return 'unpatentable'
    if 'mixed' in decs: return 'mixed'
    if 'not unpatentable' in decs: return 'not unpatentable'
    raise AssertionError(f"Unexplainable decision list {decs}")

def decision_date(decision):
    return datetime.date(
        *time.strptime(decision['decisionDate'], '%m-%d-%Y')[0:3]
    )

def patent_outcomes(patents):
    """
        Given an iterable of patents, returns a tuple summarizing all the
        outcomes. If the list of patents is empty or if there are no PTAB
        proceedings, return a single-element tuple identifying that fact.
    """
    if len(patents) == 0: return ('unpatented',)
    decs = decisions().get_multi('patent_no', patents)
    if len(decs) == 0: return ('unlitigated',)
    return tuple(sorted({
        o for dec in decs for o in decision_orders(dec, filtered = True)
    }))


def decision_bib(decision):
    """
        Creates a bibliography entry for a decision in Hereinafter format.
    """
    return "\\defadmincase{}{\n" \
            "p={" + decision['petitionerPartyName'] + "},\n" \
            "d={" + decision['respondentPartyName'] + "},\n" \
            "court=P.T.A.B.,\n" \
            "docket=" + decision['proceedingNumber'] + ",\n" \
            "date=" + decision_date(decision).strftime('%b %-d %Y') + ",\n" \
            "}\n"


if __name__ == '__main__':

    pass
