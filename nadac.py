#!/usr/bin/env python3

import re
import sys
import csv
import csvplus
import os
import agg
import analysis
import datetime

DIR = 'nadac'
SUMMARY = os.path.join(DIR, 'summary.csv')

def each_record():
    """
        Opens all the NADAC files and yields for each row of data.
    """
    for name in sorted(os.listdir(DIR)):
        if not name.startswith('nadac-'): continue
        print(name, file = sys.stderr)
        with open(os.path.join(DIR, name), newline = '') as io:
            reader = csvplus.Reader(io, dialect = 'excel')
            reader.header_proc = lambda x: x.lower().replace(' ', '_')
            for row in reader:
                yield(row)

def summarize():
    """
        Generates a summary of all the NADAC data of interest.
    """
    ndcs = { format_ndc(ndc) for ndc in analysis.relevant_ndcs() }
    recs = {
        (
            rec['ndc'],
            re.sub(r"^(\d+)/(\d+)/(\d+)$", r"\3-\1-\2", rec['effective_date']),
            rec['nadac_per_unit'],
            rec['classification_for_rate_setting'],
            rec['pricing_unit'],
        )
        for rec in each_record()
        if rec['ndc'][0:9] in ndcs or 'SEMGLEE' in rec['ndc_description']
    }
    with open(SUMMARY, 'w', newline = '') as io:
        writer = csv.writer(io, dialect = 'unix', quoting = csv.QUOTE_MINIMAL)
        writer.writerow(('ndc', 'date', 'nadac', 'class', 'unit'))
        for rec in sorted(recs):
            writer.writerow(rec)

def each_summary_record():
    """
        Reads the summary file and yields for each record.
    """
    with open(SUMMARY, newline = '') as io:
        reader = csv.DictReader(io, dialect = 'unix')
        records_by_ndc = {}
        for rec in reader:
            rec['date'] = datetime.date(
                *[ int(e) for e in rec['date'].split('-') ]
            )
            rec['nadac'] = float(rec['nadac'])
            yield(rec)

the_ndc_summary = None
def ndc_summary():
    """
        Indexes the summary by NDC (first nine digits).
    """
    global the_ndc_summary
    if the_ndc_summary is None:
        the_ndc_summary = agg.Table(list(each_summary_record()))
        the_ndc_summary.index('ndc', lambda rec: rec['ndc'][0:9])
    return the_ndc_summary


def recs_for_ndcs(ndcs):
    """
        Yields NADAC records given a list of NDCs. The NDCs should be product
        NDCs in FDA form.
    """
    ndc_set = { format_ndc(ndc) for ndc in ndcs }
    return ndc_summary().get_multi('ndc', ndc_set)

class NDCSeries:
    """
        A time series of NADAC prices for a given NDC.
    """

    MAX_DATE = datetime.date(2022, 6, 1)

    def __init__(self, ndc):
        self.ndc = ndc
        self.recs = ndc_summary().get('ndc', format_ndc(ndc))
        self.check_units()
        l = sorted(
            agg.aggregate(
                self.recs,
                lambda x: x['date'],
                postproc = lambda l: min([ e['nadac'] for e in l ])
            ).items()
        )
        self.series = [(
            l[i][0],
            l[i + 1][0] if i + 1 < len(l) else NDCSeries.MAX_DATE,
            l[i][1]
        ) for i in range(0, len(l))]

    def check_units(self):
        units = agg.aggregate(
            self.recs,
            lambda rec: rec['unit'],
            postproc = lambda recs: len(recs)
        )
        if len(units) > 1:
            print(f"Multiple units for {self.ndc}: {units}", file=sys.stderr)
            use_unit = max(units.items(), key = (lambda i: i[1]))[0]
            self.recs = [ rec for rec in self.recs if rec['unit'] == use_unit ]


    def start_date(self):
        return self.series[0][0]

    def empty(self):
        return len(self.series) == 0

    def price_on_date(self, date):
        """
        Returns the price on a given date.
        """
        if date < self.series[0][0]: return None
        if date >= NDCSeries.MAX_DATE: return None
        for start, end, price in self.series:
            if date >= start and date < end: return price
        assert False

    def prices_in_range(self, start_date, end_date):
        """
        Returns a list of prices active during the given date range.
        """
        if end_date < self.series[0][0]: return None
        if start_date >= NDCSeries.MAX_DATE: return None
        prices = []
        for start, end, price in self.series:
            if start_date < end: prices.append(price)
            if end >= end_date: break
        return prices

def remove_none(l):
    """Removes None from the given list."""
    return [ i for i in l if i is not None ]

def best_price(ndcs, date, end_date = None):
    """
        Returns the best price available for any of the NDCs on the given date.
    """
    series = [ ser for ndc in ndcs if not (ser := NDCSeries(ndc)).empty() ]
    if len(series) == 0: return None
    if end_date is None:
        prices = [
            pod for s in series if (pod := s.price_on_date(date)) is not None
        ]
    else:
        prices = [
            min(pirs) for s in series
            if (pirs := s.prices_in_range(date, end_date)) is not None
        ]
    if len(prices) == 0: return None
    return min(prices)

def price_trend(
        ndcs, start_date, num_intervals, interval = 365.25 / 4,
        stat = min, normalize = False
):
    """
        For a set of NDCs, computes price trends for num_intervals ranges of
        days thereafter. Within each interval, the statistic function is used to
        select a single price per NDC, and then to select among those prices. If
        normalize is True, then normalizes prices to 1. Returns a list mapping
        the interval number to the computed price; interval 0 is the starting
        price (or 1 if nomalized).
    """
    res = []
    series = [ ser for ndc in ndcs if not (ser := NDCSeries(ndc)).empty() ]
    if len(series) == 0: return None
    if start_date is None:
        start_date = min(s.start_date() for s in series)
    start_prices = remove_none([ s.price_on_date(start_date) for s in series ])
    if len(start_prices) == 0: return None
    start_price = stat(start_prices)
    res.append(1 if normalize else start_price)
    normal = start_price if normalize else 1

    for i in range(0, num_intervals):
        s = start_date + datetime.timedelta(days = round(i * interval))
        e = start_date + datetime.timedelta(days = round((1 + i) * interval))
        prices = remove_none([ ser.prices_in_range(s, e) for ser in series ])
        if len(prices) == 0: res.append(None)
        else: res.append(stat([ stat(p) / normal for p in prices ]))
    return res


def yearly_costs_by_ndc(ndcs):
    """
        Returns the average NADAC per year for each package NDC in the given
        product NDC list.
    """
    return agg.aggregate(
        recs_for_ndcs(ndcs), lambda x: x['ndc'],
        postproc = lambda l: agg.aggregate(
            l, lambda x: int(x['date'].split("-")[0]),
            lambda x: float(x['nadac']),
            postproc = lambda l: round(sum(l) / len(l), 2)
        )
    )

def yearly_costs(ndcs, use_min = False):
    if use_min:
        pp = lambda l: round(min(l), 2)
    else:
        pp = lambda l: round(sum(l) / len(l), 2)
    return agg.aggregate(
        recs_for_ndcs(ndcs),
        lambda x: x['date'].year,
        lambda x: x['nadac'],
        postproc = pp
    )

def all_costs(ndcs):
    """
        Given a list of NDCs, returns a list of cost arrays. Each cost array is
        a list of tuples, containing the date and the cost on that date.
    """
    return [
        sorted([
            (rec['date'].isoformat(), rec['nadac'])
            for rec in recs
        ])
        for ndc in ndcs
        if len(recs := ndc_summary().get('ndc', format_ndc(ndc))) > 0
    ]

def format_ndc(ndc):
    """
        Takes an FDA formatted NDC and turns it into a HIPAA formatted NDC. Note
        that the two package code digits are not included in either.
    """
    if m := re.match(r"^(\d{4,5})-([N\d]\d{2,3})$", ndc):
        return m[1].rjust(5, '0') + m[2].rjust(4, '0')
    else:
        raise AssertionError("ndc " + ndc + " does not match pattern")

if __name__ == '__main__':
    summarize()
