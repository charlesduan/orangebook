#!/usr/bin/env python3

import sys
import os
import re
import csv
import functools
import csvplus
import agg
import json
import collections
import datetime
import time

OBDATA = 'obdata'
PAT_SUMMARY = os.path.join(OBDATA, 'patent-summary.csv')
PROD_SUMMARY = os.path.join(OBDATA, 'product-summary.csv')
EQUIV_SUMMARY = os.path.join(OBDATA, 'equivalents.json')

########################################################################
#
# DATA STRUCTURES
#
########################################################################

class ApplicationTuple(collections.namedtuple(
        "ApplicationTuple", [ "appl_no", "product_no" ]
    )):
    """
        A tuple of an application-product number pair.
    """
    def __repr__(self):
        return f"App<{self.appl_no}.{self.product_no}>"



FormulationTuple = collections.namedtuple(
    "FormulationTuple", [ "ingredient", "form_route", "strength" ]
)
FormulationTuple.__doc__ = """
    A tuple identifying a drug formulation. Based on the definition of
    pharmaceutical equivalence, the tuple contains the active ingredient(s), the
    form/route, and the strength.
    """

def app_tuple(row):
    return ApplicationTuple(row['appl_no'], row['product_no'])

def form_tuple(row):
    """
    Produces the tuple for a drug's active ingredient, form/route, and strength.
    """
    form_route = re.sub("; ", ";", row['df;route'])
    ingredients = re.split(r";\s*", row['ingredient'])
    strengths = parse_strengths(row['strength'], len(ingredients), row)

    # The ingredient list needs to be sorted for canonicalization. However, the
    # strengths correspond in order with the ingredient list, so they must be
    # sorted together.
    if len(ingredients) == 1:
        ingredients *= len(strengths)
    if len(ingredients) != len(strengths):
        raise AssertionError(
            f"Different lengths in {row}: {ingredients}, {strengths}"
        )

    ingredients, strengths = zip(*sorted(zip(ingredients, strengths)))

    return FormulationTuple(
        "; ".join(ingredients), form_route,
        "; ".join(strengths)
    )

def parse_strengths(text, exp_len, row):
    text = re.sub(r" \*\*Federal Register.*$", "", text)
    if text == "250.0MG;12.5MG;75.0MG;EQ 250MG BASE,N/A,N/A,N/A; " \
            "N/A,12.5MG,75MG,50MG":
        return [ '250MG', '12.5MG', '75MG', '50MG' ]

    if m := re.search(r"^(.*;.*?)\s*\((.*;.*)\)", text):
        return [
            f"{a} ({b})"
            for a, b in zip(re.split(r";\s*", m[1]), re.split(r";\s*", m[2]))
        ]
    else:
        elts = re.split(r";\s*", text)
        if len(elts) == exp_len or exp_len == 1: return elts
        relts = [ ", ".join(e) for e in zip(*[ e.split(",") for e in elts ]) ]
        if len(relts) == exp_len:
            return relts
        if len(elts) % exp_len == 0:
            res = [
                ", ".join(elts[i:(i + exp_len)])
                for i in range(0, len(elts), len(elts) // exp_len)
            ]
            return res
        raise RuntimeError(f"Can't parse {text} into {exp_len} elts for {row}")


########################################################################
#
# EQUIVALENCE CLASSES
#
########################################################################


class EquivalenceClass:
    """
        In reading FDA Orange Books, this class determines and aggregates drugs
        that the FDA considers "equivalent". This deals with the fact that
        across Orange Books, the FDA is not consistent in identifying drug
        formulations.

        Two assumptions are made:

          - Within a single Orange Book file, items with the same formulation
            tuple are pharmaceutical equivalents. Thus, while reading a single
            file, it is possible to determine equivalence among multiple
            applications based on the formulation tuple.

          - Across Orange Book files, if the formulation tuple is the same, then
            the products are equivalents. The converse is not necessarily true.
            But the combination of this and the above principle mean that if a
            formulation tuple is the same for two records, then they are
            equivalents.

          - Across Orange Book files, application tuples are stable. That is, an
            application number always refers to the same application over time,
            and the product number always identifies the same product within the
            application.

    """

    eq_classes = {}
    next_eq_id = 0
    form_tuple_classes = {}
    app_tuple_classes = {}

    def __init__(self, form_tuples, app_tuples, eq_id = None):
        self.form_tuples = set()
        self.app_tuples = set()

        for ft in form_tuples: self.add_form_tuple(ft)
        for at in app_tuples: self.add_app_tuple(at)

        if eq_id is None:
            eq_id = EquivalenceClass.next_eq_id
            EquivalenceClass.next_eq_id += 1
        else:
            EquivalenceClass.next_eq_id = max(
                EquivalenceClass.next_eq_id, eq_id + 1
            )
        assert eq_id not in EquivalenceClass.eq_classes
        self.eq_id = eq_id
        EquivalenceClass.eq_classes[self.eq_id] = self

    def add_form_tuple(self, form_tuple):
        assert type(form_tuple) is FormulationTuple
        if form_tuple in EquivalenceClass.form_tuple_classes:
            raise AssertionError(
                f"Multiple equivalence classes for {form_tuple}"
            )
        EquivalenceClass.form_tuple_classes[form_tuple] = self
        self.form_tuples.add(form_tuple)

    def add_app_tuple(self, app_tuple):
        assert type(app_tuple) is ApplicationTuple
        if app_tuple in EquivalenceClass.app_tuple_classes:
            raise AssertionError(
                f"Multiple equivalence classes for {app_tuple}: "
                f"{self}, {EquivalenceClass.app_tuple_classes[app_tuple]}"
            )
        EquivalenceClass.app_tuple_classes[app_tuple] = self
        self.app_tuples.add(app_tuple)

    def append(self, form_tuple, app_tuple):
        """
            Adds a row from an OB product file to this equivalence class. It
            must be equivalent in the sense that either the app tuple or the
            form tuple must be known to this equivalence class already.
        """
        if app_tuple in self.app_tuples:
            if form_tuple in self.form_tuples: return
            self.add_form_tuple(form_tuple)
        elif form_tuple in self.form_tuples:
            self.add_app_tuple(app_tuple)
        else:
            raise AssertionError("Neither form nor app tuple matched")

    def merge(self, other_eq_class):
        """
            Merges another equivalence class into this one on the discovery that
            they ought to be combined. The other_eq_class is then removed from
            the list of classes.
        """
        self.form_tuples.update(other_eq_class.form_tuples)
        for ft in other_eq_class.form_tuples:
            EquivalenceClass.form_tuple_classes[ft] = self
        self.app_tuples.update(other_eq_class.app_tuples)
        for at in other_eq_class.app_tuples:
            EquivalenceClass.app_tuple_classes[at] = self
        del(EquivalenceClass.eq_classes[other_eq_class.eq_id])

    def to_dict(self):
        return {
            'eq_id': self.eq_id,
            'form_tuples': sorted(self.form_tuples),
            'app_tuples': sorted(self.app_tuples),
        }

    def one_form_tuple(self):
        """
            Returns one form tuple from this class, for use in user displays.
        """
        return sorted(self.form_tuples)[0]

    def __repr__(self):
        return f"EquivalenceClass{self.to_dict()}"

    def __str__(self):
        canon_form = self.one_form_tuple()
        return f"Class <{canon_form.ingredient}, {canon_form.strength}> " \
                f"({len(self.form_tuples)} form, {len(self.app_tuples)} app)"

    @classmethod
    def add(cls, row):
        """
            Adds a row to an appropriate equivalence class, creating it if
            necessary.
        """
        ft, at = form_tuple(row), app_tuple(row)
        ftc = cls.get(ft)
        atc = cls.get(at)
        if ftc is None and atc is None:
            return cls((ft,), (at,))
        elif atc is None:
            ftc.append(ft, at)
            return ftc
        elif ftc is None:
            atc.append(ft, at)
            return atc
        elif atc is ftc:
            ftc.append(ft, at)
            return ftc
        else:
            ftc.merge(atc)
            ftc.append(ft, at)
            return ftc

    @classmethod
    def all(cls):
        return cls.eq_classes.values()

    @classmethod
    def get(cls, tup):
        """
            Retrieves the equivalence class for the given tuple. Either a
            formulation tuple or an application tuple may be given, or an
            integer for an equivalence class ID.
        """
        if type(tup) is FormulationTuple:
            return cls.form_tuple_classes.get(tup, None)
        elif type(tup) is ApplicationTuple:
            return cls.app_tuple_classes.get(tup, None)
        elif type(tup) is int:
            return cls.eq_classes[tup]
        else:
            raise AssertionError(f"Invalid tuple type {type[tup]}")

    @classmethod
    def has(cls, tup):
        if type(tup) is FormulationTuple:
            return tup in cls.form_tuple_classes
        elif type(tup) is ApplicationTuple:
            return tup in cls.app_tuple_classes
        else:
            raise AssertionError(f"Invalid tuple type {type[tup]}")

    @classmethod
    def __len__(cls):
        return len(cls.eq_classes)


########################################################################
#
# DATA SUMMARIZATION
#
########################################################################

def each_book():
    """
    Yields (name, product_csv, patent_csv) for each Orange Book in the
    directory.
    """
    for name in sorted(os.listdir(OBDATA)):
        if not name.startswith('EOBZIP_'): continue
        prodpath = os.path.join(OBDATA, name, 'products.txt')
        patpath = os.path.join(OBDATA, name, 'patent.txt')
        print(name, file = sys.stderr)

        with open(prodpath, newline = '') as prodio, \
                open(patpath, newline = '') as patio:
            prodreader = csvplus.Reader(prodio, delimiter = '~')
            prodreader.header_proc = lambda x: x.lower()
            patreader = csvplus.Reader(patio, delimiter = '~')
            patreader.header_proc = lambda x: x.lower()

            yield name, prodreader, patreader

def summarize():
    """
        Summarizes all the Orange Books. This does two things:

          - For patent files, it consolidates unique application tuples and
            patent numbers, and writes them to the patent summary file.

          - For product files, it reads each record and assigns it to an
            equivalence class. After reading everything, the equivalence classes
            are written out.
    """
    pat_headers = ('appl_no', 'product_no', 'patent_no')
    prod_headers = (
        'appl_no', 'product_no', 'approval_date', 'te_code', 'applicant'
    )
    with csvplus.UniqueRowWriter(PAT_SUMMARY) as patwriter, \
            csvplus.UniqueRowWriter(PROD_SUMMARY) as prodwriter:

        patwriter.write_header(pat_headers)
        prodwriter.write_header(prod_headers)
        for book, prodreader, patreader in each_book():
            for row in patreader:
                if row['patent_no'] == '': continue
                if row['patent_no'].endswith('*PED'): continue
                patwriter.writerow([ row[h] for h in pat_headers ])
            for row in prodreader:
                EquivalenceClass.add(row)
                prodwriter.writerow([ row[h] for h in prod_headers ])

    with open(EQUIV_SUMMARY, 'w') as eqio:
        json.dump(
            [ eq_class.to_dict() for eq_class in EquivalenceClass.all() ],
            eqio
        )

all_patents = None
all_products = None
def load_summary():
    global all_patents, all_products
    if len(EquivalenceClass.eq_classes) == 0:
        with open(EQUIV_SUMMARY) as io:
            for r in json.load(io):
                EquivalenceClass(
                    [ FormulationTuple(*x) for x in r['form_tuples'] ],
                    [ ApplicationTuple(*x) for x in r['app_tuples'] ],
                    eq_id = r['eq_id'],
                )

    if all_patents is None:
        l = []
        with open(PAT_SUMMARY, newline = '') as io:
            reader = csvplus.Reader(io, dialect = 'unix')
            for row in reader:
                row.app_tuple = ApplicationTuple(
                    row['appl_no'], row['product_no']
                )
                if EquivalenceClass.has(row.app_tuple): l.append(row)
        all_patents = agg.Table(l)
        all_patents.index('patent_no')
        all_patents.index('app_tuple', lambda x: x.app_tuple)

    if all_products is None:
        with open(PROD_SUMMARY, newline = '') as io:
            reader = csvplus.Reader(io, dialect = 'unix')
            all_products = agg.Table(list(reader))
        for row in all_products:
            row.app_tuple = app_tuple(row)
            row.eq_class = EquivalenceClass.get(row.app_tuple)
            if row['approval_date'] == 'Approved Prior to Jan 1, 1982':
                row.approval_date = datetime.date(1982, 1, 1)
            else:
                row.approval_date = datetime.date(
                        *time.strptime(row['approval_date'], '%b %d, %Y')[0:3]
                )
        all_products.index('app_tuple', lambda x: x.app_tuple)
        all_products.index('eq_id', lambda x: x.eq_class.eq_id)

########################################################################
#
# DATA USE
#
########################################################################

def each_formulation():
    """
        Returns an iterator for each formulation tuple.
    """
    return EquivalenceClass.form_tuple_classes.keys()

def patent_recs(patent):
    """
        Returns a list of Orange Book patent records given a patent number.
    """
    return all_patents.get('patent_no', patent)

def app_product_recs(app_tuples):
    """
        Returns Orange Book product records given an application tuple.
    """
    return all_products.get_multi('app_tuple', app_tuples)

def form_product_recs(form_tuples):
    """
        Returns Orange Book product records given a list of form_tuples.
    """
    return all_products.get_multi('form_tuple', form_tuples)

def patents_for_eq_class(eq_class):
    """
        Returns all patents for an equivalence class.
    """
    return {
        rec['patent_no']
        for rec in all_patents.get_multi('app_tuple', eq_class.app_tuples)
    }

def eq_classes_with_patent():
    """
        Returns all equivalence classes that have at least one associated
        patent.
    """
    return [
        eq
        for eq in EquivalenceClass.all()
        if len(patents_for_eq_class(eq)) > 0
    ]

def eqs_for_patent(patno):
    """
        Returns equivalence classes matching a given patent number.
    """
    return {
        EquivalenceClass.get(pr.app_tuple)
        for pr in patent_recs(patno)
    }

all_a_rated_app_tuples = None

def is_a_rated(app_tuple):
    """
        Returns whether the given app tuple is an A-rated therapeutic
        equivalent. It is if there is at least one OB record with an A rating.
    """
    global all_a_rated_app_tuples
    if all_a_rated_app_tuples is None:
        all_a_rated_app_tuples = {
            r.app_tuple for r in all_products
            if r['te_code'].startswith('A')
        }
    return app_tuple in all_a_rated_app_tuples

def equivalent_app_tuples(app_tuple, a_only = True):
    """
        Returns app tuples equivalent to the given one. If a_only is True, then
        only A-rated ones are returned.
    """
    if a_only:
        return [
            at for at in EquivalenceClass.get(app_tuple).app_tuples
            if is_a_rated(at)
        ]
    else:
        return EquivalenceClass.get(app_tuple).app_tuples

def approval_date(app_tuple):
    recs = app_product_recs([ app_tuple ])
    if len(recs) == 0: raise AssertionError(f"Empty recs for {app_tuple}")
    return min(r.approval_date for r in recs)

def generics_for_classes(eq_classes, a_only = True, exclude = None):
    """
        Returns generic records from the Orange Book product file matching the
        given equivalence classes. This is similar to form_product_recs() with
        two additional features.

        First, it can restrict the result to A-rated equivalents.

        Second, a list of application tuples can be given, and records with
        those application tuples will be excluded from the result. This can be
        used to exclude the brand-name records from the resulting list.
    """
    if exclude is None: exclude = set()
    app_tuples = set().union(*[
        at for c in eq_classes
        for at in c.app_tuples if at not in exclude
    ])
    recs = app_product_recs(app_tuples)
    if a_only:
        return { r for r in recs if r['te_code'].startswith('A') }
    else:
        return recs


if __name__ == '__main__':

    summarize()
