#!/usr/bin/env python3

"""
    Functions for extracting data across multiple data sources of the Orange
    Book/PTAB study.
"""

import re
import sys
import ptab
import ob
import ndc
import agg
import nadac
import match_ndc_ob as mno
import statistics
import time
import datetime


ob.load_summary()
ndc.load_summary()

the_ob_ptab_decisions = None

def ob_ptab_decisions():
    """
        Returns an agg.Table of PTAB decision records, where the litigated
        patent is found in the Orange Book.
    """
    global the_ob_ptab_decisions
    if the_ob_ptab_decisions is None:
        obpats = ob.all_patents
        res = ptab.decisions_for_patents(
            ob.all_patents.indexed_values('patent_no')
        )
        ptab.check_decisions_for_text(res)
        res = agg.Table(res)
        res.index('patent_no', lambda x: x['respondentPatentNumber'])
        res.index('outcome', lambda x: x['outcome'])
        the_ob_ptab_decisions = res
    return the_ob_ptab_decisions

def ptab_app_tuples(outcome = None):
    """
        Finds all application tuples associated with at least one PTAB
        challenged patent. For each application tuple, finds all patents
        associated with it and separates those patents into PTAB-challenged and
        unchallenged patents.
    """
    ptab_patents = ob_ptab_decisions().indexed_values('patent_no')
    if outcome is not None:
        ptab_patents = [
            p for p in ptab_patents if ptab.patent_outcome(p) == outcome
        ]

    app_tuples = {
        r.app_tuple for r in ob.all_patents.get_multi('patent_no', ptab_patents)
    }
    return {
        at: patent_data_for_app_tuple(at)
        for at in app_tuples
    }

def ptab_equivalence_classes(outcome = None):
    """
        Finds all equivalence classes in which at least one application tuple is
        associated with a PTAB-litigated patent.
    """
    return [
        ob.EquivalenceClass.get(eqid)
        for eqid in {
            ob.EquivalenceClass.get(at).eq_id
            for at in ptab_app_tuples(outcome).keys()
        }
    ]

def patent_data_for_app_tuple(app_tuple):
    patents = {
        r['patent_no'] for r in ob.all_patents.get('app_tuple', app_tuple)
    }
    return agg.aggregate(patents, lambda p: ptab.patent_outcome(p))

def ndc_records_for_ob_forms(eq_class):
    """
        Returns the NDC records relevant to a given formulation.
    """
    ndc_recs = {
        rec
        for app_tuple in eq_class.app_tuples
        for rec in ndc.recs_for_appno(app_tuple.appl_no)
    }
    return {
        ndc_rec for ndc_rec in ndc_recs
        if mno.equivalent(eq_class, ndc_rec.form_tuple)
    }

def ndcs_for_equivalence_class(eq_class):
    """
        Returns all the NDCs for an equivalence class.
    """
    assert(type(eq_class) is ob.EquivalenceClass)
    return { ndc_rec['ndc'] for ndc_rec in ndc_records_for_ob_forms(eq_class) }


def yearly_approvals(eq_class, start = 2013, end = 2023):
    years = [
        min({
            int(re.search(r"\d{4}", r['approval_date'])[0])
            for r in ob.app_product_recs((at,))
        })
        for at in eq_class.app_tuples
    ]
    return {
        test_y: len([ 1 for y in years if y <= test_y ])
        for test_y in range(start, end)
    }


def yearly_products(eq_class, start = 2013, end = 2023):
    """
        Returns a dict of each year between start and end, mapped to the number
        of NDC records active during that year for the given equivalence class
        of OB forms.
    """
    ranges = [
        (
            int(ndc_rec['start_file'].split('-')[0]),
            int(ndc_rec['end_file'].split('-')[0])
        )
        for ndc_rec in ndc_records_for_ob_forms(eq_class)
    ]
    return {
        year: len([
            1 for r in ranges if year >= r[0] and year <= r[1]
        ])
        for year in range(start, end)
    }

def yearly_min_nadac(eq_class):
    """
        Computes the average NADAC price in a year for a given formulation
        equivalence class.
    """
    ndcs = { rec['ndc'] for rec in ndc_records_for_ob_forms(eq_class) }
    return nadac.yearly_costs(ndcs, True)

def yearly_nadac(eq_class):
    """
        Computes the average NADAC price in a year for a given formulation
        equivalence class.
    """
    ndcs = { rec['ndc'] for rec in ndc_records_for_ob_forms(eq_class) }
    return nadac.yearly_costs(ndcs)


def formulation_ptab_outcomes(*args):
    """
        Each formulation tuple can be associated with one or more PTAB
        dispositions by finding the patents associated with the formulation and
        then finding all the PTAB orders associated with those patents. With no
        arguments, shows the number of Orange Book formulations with each set of
        PTAB dispositions. If an argument is given, then it should be the PTAB
        disposition to be found; returns a list of formulation tuples with that
        PTAB disposition.
    """
    class_outcomes = {
        eq_class.eq_id: ptab.patent_outcomes(ob.patents_for_eq_class(eq_class))
        for eq_class in ob.EquivalenceClass.all()
    }
    if len(args) == 0:
        return agg.aggregate(
            class_outcomes.items(),
            lambda x: x[1],
            postproc = lambda l: len(l)
        )
    else:
        return [
            ob.EquivalenceClass.get(eq_id)
            for eq_id, outcomes in class_outcomes.items()
            if outcomes == args
        ]


def ptab_report(decision):
    """
        Prints a report on a patent PTAB decision.
    """
    patno = decision['respondentPatentNumber']
    print(f"Proceeding {decision['proceedingNumber']}, Patent {patno}")
    print(f"Decided: {decision['decisionDate']}")
    print(f"Held: {','.join(ptab.decision_orders(decision, filtered = True))}")
    print("")
    info = patent_info(patno)
    print(f"{len(info)} formulation{'s' if len(info) != 1 else ''}")
    for form_tuple, data in info.items():
        print(
            f"  {form_tuple.ingredient.capitalize()}, "
            f"{form_tuple.strength.lower()}:")
        ndcs = data['ndcs']
        gndcs = data['generic_ndcs']
        print(f"    {len(ndcs)} NDC{'s' if len(ndcs) != 1 else ''}")
        print(f"    {len(gndcs)} generic NDC{'s' if len(gndcs) != 1 else ''}")

def ptab_cites_for_eq_class(eq_class):
    if type(eq_class) is int: eq_class = ob.EquivalenceClass.get(eq_class)
    patents = ob.patents_for_eq_class(eq_class)
    decisions = sorted(
        ptab.decisions_for_patents(patents), 
        key = lambda d: d['proceedingNumber']
    )
    for d in decisions:
        print(ptab.decision_bib(d))


def eq_class_report(eq_class):
    """
        Produces a report on an OB equivalence class.
    """
    if type(eq_class) is int: eq_class = ob.EquivalenceClass.get(eq_class)

    form_tuple = eq_class.one_form_tuple()
    print(
        f"{form_tuple.ingredient.capitalize()}, "
        f"{form_tuple.strength.lower()} "
        f" (EQ class #{eq_class.eq_id}):"
    )
    patents = ob.patents_for_eq_class(eq_class)
    print(f"  Patents: {len(patents)}")
    decisions = ptab.decisions_for_patents(patents)
    print(f"  PTAB decisions: {len(decisions)}")
    for d in decisions:
        print(
            f"    {d['proceedingNumber']} ({d['decisionDate']}): "
            f"{', '.join(ptab.decision_orders(d, filtered = True))}"
        )
        # print(f"      {ptab.decision_url(d)}")
        for a in d['appeals']:
            print(f"      Appeal: {a['print_name']}, {a['dispgeneral']}")

    mat = agg.Matrix(range(2013, 2023))
    mat.add('Approval', yearly_approvals(eq_class))
    mat.add('NDCs', yearly_products(eq_class))
    mat.add('NADAC', yearly_nadac(eq_class))
    mat.add('Min NADAC', yearly_min_nadac(eq_class))
    mat.print()

def relevant_ndcs():
    """
    Returns a list of every NDC potentially relevant to a PTAB decision.
    """
    ptab_patents = ob_ptab_decisions()
    print(f"Got {len(ptab_patents)} patents", file = sys.stderr)

    eq_classes = {
        eq_class
        for patno in ptab_patents.indexed_values('patent_no')
        for eq_class in ob.eqs_for_patent(patno)
    }
    print(f"Got {len(eq_classes)} equivalence classes", file = sys.stderr)

    applications = {
        app_tuple.appl_no
        for c in eq_classes for app_tuple in c.app_tuples
    }
    print(f"Found {len(applications)} applications.", file = sys.stderr)

    ndcs = {
        rec['ndc']
        for appno in applications for rec in ndc.recs_for_appno(appno)
    }
    print(f"Found {len(ndcs)} NDCs.", file = sys.stderr)

    return ndcs

def products_per_equivalence_class(a_only = False):
    """
        Returns a matrix of statistics on products per equivalence class, for
        various selections of equivalence classes.
    """
    prods_per_eq = agg.Matrix(['Mean', 'Std.\ Dev.', 'n'], 'Formulations')
    def add_ppe(name, eqs):
        if a_only:
            data = [
                sum(ob.is_a_rated(at) for at in eq.app_tuples) for eq in eqs
            ]
        else:
            data = [ len(eq.app_tuples) for eq in eqs ]
        prods_per_eq.add(
            name, [
                round(statistics.mean(data), 2),
                round(statistics.stdev(data), 2),
                len(data)
            ]
        )
    add_ppe('All', ob.EquivalenceClass.all())
    add_ppe('Patented', ob.eq_classes_with_patent())
    add_ppe('PTAB Challenged', ptab_equivalence_classes())
    add_ppe('Held Unpatentable', ptab_equivalence_classes('unpatentable'))
    add_ppe('Not Patentable', ptab_equivalence_classes('not unpatentable'))
    add_ppe('Mixed Outcome', ptab_equivalence_classes('mixed'))
    return prods_per_eq

def ptab_approval_date_delta(decision, a_only = True):
    """
        Given a PTAB decision, returns a list of date deltas between the
        decision and subsequent generic approvals.
    """
    dec_date = ptab.decision_date(decision)
    eqs = ob.eqs_for_patent(decision['respondentPatentNumber'])
    app_tuples = { at for eq in eqs for at in eq.app_tuples }
    if a_only:
        app_tuples = { at for at in app_tuples if ob.is_a_rated(at) }
    return [
        (ob.approval_date(at) - dec_date).days
        for at in app_tuples if ob.approval_date(at) >= dec_date
    ]

def generic_approvals_after_ptab(decisions, years = range(1, 6), a_only = True):
    """
        For a given list of decisions, determines the mean number of generics
        approved a given number of years after those decisions.
    """
    m = []
    for decision in decisions:
        deltas = ptab_approval_date_delta(decision, a_only)
        m.append(stratify_deltas(deltas, years))

    return {
        year: statistics.mean([ r[year] for r in m ]) for year in years
    }

def stratify_deltas(deltas, years):
    return {
        year: sum(d <= year * 365 for d in deltas)
        for year in years
    }

def approval_to_decision_time():
    """
        For each app tuple associated with a PTAB decision, computes the
        difference between that app tuple's approval date and the PTAB decision
        date.
    """
    deltas = []
    for dec in ob_ptab_decisions():
        app_tuples = {
            r.app_tuple for r in ob.patent_recs(dec['respondentPatentNumber'])
        }
        deltas.append(max([
            (ptab.decision_date(dec) - ob.approval_date(at)).days
            for at in app_tuples
        ]))
    return deltas

def generic_approvals_after_control(
        years = range(1, 6),
        mean_ptab_time = statistics.mean(approval_to_decision_time()),
        a_only = True
):
    """
        Assuming a hypothetical PTAB challenge brought
        mean(approval_to_decision_time()) days after approval of each patented
        drug product, computes the number of generic entrants for certain
        numbers of years thereafter.
    """
    m = []
    for app_tuple in ob.all_patents.indexed_values('app_tuple'):
        hypo_date = ob.approval_date(app_tuple) + \
                datetime.timedelta(days = mean_ptab_time)
        if hypo_date > datetime.date(2022 - max(years), 1, 1): continue
        m.append(stratify_deltas([
            (ob.approval_date(at) - hypo_date).days
            for at in ob.equivalent_app_tuples(app_tuple, a_only)
            if ob.approval_date(at) >= hypo_date
        ], years))
    return {
        year: statistics.mean([ r[year] for r in m ]) for year in years
    }

def equivalence_class_price_trends(eqs):
    """
        Computes average price trends for equivalence classes, benchmarked to
        their earliest known price.
    """
    trends = [
        pt for eq in eqs
        if None is not (pt := nadac.price_trend(
            ndcs_for_equivalence_class(eq), start_date = None,
            num_intervals = 10, interval = 365.25, normalize = True
        ))
    ]
    if len(trends) == 0: return None
    return [
        statistics.mean(compact_list)
        if len(compact_list := [ i for i in plist if i is not None ]) > 0
        else None
        for plist in zip(*trends)
    ]

def equivalence_class_ptab_date_pairs(decisions):
    """
        Returns all unique pairs of equivalence classes and PTAB decision dates
        for equivalence classes of relevance to the given decisions.
    """
    return {
        (eq, ptab.decision_date(dec))
        for dec in decisions
        for eq in ob.eqs_for_patent(dec['respondentPatentNumber'])
    }

def ptab_decision_price_trends(decisions):
    """
        Computes average price trends for equivalence classes involving a
        PTAB-litigated patent, benchmarked to the price on the date of the PTAB
        decision.
    """
    trends = [
        pt for eq, date in equivalence_class_ptab_date_pairs(decisions)
        if None is not (pt := nadac.price_trend(
            ndcs_for_equivalence_class(eq),
            start_date = date,
            num_intervals = 20, interval = 365.25 / 4, normalize = True
        ))
    ]
    if len(trends) == 0: return None
    return [
        statistics.mean(compact_list)
        if len(compact_list := [ i for i in plist if i is not None ]) > 0
        else None
        for plist in zip(*trends)
    ]

def eqs_with_appeals():
    decisions = [ d for d in ob_ptab_decisions() if 'appeals' in d ]
    eqs = { eq for eq, date in equivalence_class_ptab_date_pairs(decisions) }
    ingredients = set()
    for eq in sorted(eqs, key = str):
        if eq.one_form_tuple().ingredient not in ingredients:
            print()
            eq_class_report(eq)
            ingredients.add(eq.one_form_tuple().ingredient)
    print(f"{len(ingredients)} distinct ingredients found.")


def eqs_with_price_drops(decisions, years = 5, threshold = 0.5):
    """
        Returns equivalence classes implicated by the PTAB decisions given,
        where the price dropped by at least a given amount subsequent to the
        decision.

        Args:
            decisions: List of PTAB decision objects.
            years: Number of years to look for prices through.
            threshold: Fraction by which price must drop to be included.
    """

    ingredients = set()
    pairs = sorted(
        equivalence_class_ptab_date_pairs(decisions),
        key = lambda p: str(p[0])
    )
    for eq, dec_date in pairs:
        ndcs = ndcs_for_equivalence_class(eq)
        dec_date_price = nadac.best_price(ndcs, dec_date)
        if dec_date_price is None: continue
        later_date = dec_date.replace(year = dec_date.year + years)
        later_date_price = nadac.best_price(ndcs, dec_date, later_date)
        if later_date_price is None: continue
        if later_date_price > dec_date_price * (1.0 - threshold): continue

        if eq.one_form_tuple().ingredient not in ingredients:
            print("")
            eq_class_report(eq)
            ingredients.add(eq.one_form_tuple().ingredient)

        print(f"For {eq}, #{dec_date}: {dec_date_price} -> {later_date_price}")

def ptab_price_change(decisions, years = 5, window = 100, zero = False):
    """
        Determines price changes for all equivalence classes implicated by the
        PTAB decisions given.
    """
    res = []
    for eq, dec_date in equivalence_class_ptab_date_pairs(decisions):
        ndcs = ndcs_for_equivalence_class(eq)
        dec_date_price = nadac.best_price(ndcs, dec_date)
        if dec_date_price is None: continue

        later_date = dec_date.replace(year = dec_date.year + years) - \
            datetime.timedelta(days = round(window / 2))
        later_date_price = nadac.best_price(
            ndcs, later_date, later_date + datetime.timedelta(days = window)
        )
        if later_date_price is None: continue
        res.append(later_date_price / dec_date_price)
    if zero: res = [ x - 1 for x in res ]
    return res

if __name__ == "__main__":

    print(patent_info('8642077'))
