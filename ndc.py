#!/usr/bin/env python3

import re
import os
import sys
import csv
import csvplus
import agg
import functools
import collections

DIR = 'ndc'
SUMMARY = os.path.join(DIR, 'summary.csv')

def each_record():
    """
    Reads and yields for each record in the data files.
    """
    for name in sorted(os.listdir(DIR)):
        if not name.startswith('ndc-'): continue
        print(name, file = sys.stderr)
        prodpath = os.path.join(DIR, name, 'product.txt')
        with open(prodpath, newline = '', encoding = 'cp1252') as prodio:
            prodreader = csvplus.Reader(prodio, delimiter = "\t")
            prodreader.header_proc = lambda x: x.lower()
            for row in prodreader:
                row['file'] = name
                yield(row)

def consolidate_records():
    """
        When combining the NDC files, it is possible that there will be multiple
        inconsistent records for a single NDC. Testing using the consistency
        function below suggests that fewer than 10% of records are inconsistent.
        Nevertheless, it is necessary to consolidate and reconcile the records.
        The following procedure is used:

          - It is assumed that the pair (appl_no, ndc) is a unique identifier
            for records. In some cases an NDC is associated with multiple
            applications, perhaps because the drug needed reapproval or because
            the manufacturer switched the basis of approval.

          - For each unique identifier, the last data for the ingredient, form,
            route, and strength are used. The assumption is that the FDA cleans
            up its data over time.

          - The start date is the earliest start date found. The end date is the
            last end date found, on the theory that the manufacturer might push
            around the end date.

          - We also keep track of the first and last file in which the unique
            identifier is found. This may prove to be a better determinant of
            the marketing dates.

    """
    recs = {}
    for row in each_record():
        appno = row['applicationnumber']
        if appno == '': continue
        if appno.startswith('part'): continue
        if appno.startswith('Part'): continue
        if row['dosageformname'] == 'KIT': continue
        if row['substancename'] == 'WATER': continue
        identifier = (row['productndc'], appno)
        appno = re.sub(r"^[A-Z]+", "", appno)
        if identifier in recs:
            lastrec = recs[identifier]
            recs[identifier] = (
                row['productndc'], appno,
                row['substancename'], row['dosageformname'], row['routename'],
                row['active_numerator_strength'], row['active_ingred_unit'],
                min(row['startmarketingdate'], lastrec[7]),
                row['endmarketingdate'],
                lastrec[9],
                row['file'].removeprefix('ndc-'),
            )
        else:
            recs[identifier] = (
                row['productndc'], appno,
                row['substancename'], row['dosageformname'], row['routename'],
                row['active_numerator_strength'], row['active_ingred_unit'],
                row['startmarketingdate'], row['endmarketingdate'],
                row['file'].removeprefix('ndc-'),
                row['file'].removeprefix('ndc-'),
            )
    return recs

def summarize_records():
    """
    Constructs a summary of the records based on consolidate_records().
    """
    with open(SUMMARY, 'w', newline = '') as io:
        writer = csv.writer(io, dialect = 'unix', quoting=csv.QUOTE_MINIMAL)
        writer.writerow((
            'ndc', 'appl_no',
            'ingredient', 'form', 'route',
            'strength_num', 'strength_unit',
            'start_date', 'end_date', 'start_file', 'end_file'
        ))
        for row in consolidate_records().values():
            writer.writerow(row)

summary_records = None
def load_summary():
    """
    Loads the summary file.
    """
    global summary_records
    if summary_records is None:
        summary_records = agg.Table([])
        with open(SUMMARY, newline = '') as io:
            reader = csvplus.Reader(io, dialect = 'unix')
            for row in reader: summary_records.append(row)
    augment_data()
    print("Loaded NDC summary.", file = sys.stderr)

def augment_data():
    for row in summary_records:
        row.form_tuple = form_tuple(row)
    summary_records.index('form_tuple', lambda x: x.form_tuple)
    summary_records.index('ndc')
    summary_records.index('appl_no')

def form_tuple(record):
    unit = re.sub(r"/1$", "", record['strength_unit'].upper())
    if unit.startswith('.'): unit = '0' + unit
    return FormulationTuple(record['ingredient'],
            record['form'] + ';' + record['route'],
            record['strength_num'],
            record['strength_unit'])

def recs_for_appno(appno):
    """
    Returns NDC records matching the given application number.
    """
    return summary_records.get('appl_no', appno)

FormulationTuple = collections.namedtuple(
    "FormulationTuple",
    [ "ingredient", "form_route", "strength_num", "strength_unit" ]
)

if __name__ == '__main__':
    summarize_records()


