#!/usr/bin/env python3

import sys
import ptab
import ob
import ndc
import agg
import random
import match_ndc_ob as mno

ob.read_summary()
ndc.load_summary()

print("Read data.")

find_nonequivalents = True
find_equivalents = False
generics = True

if len(sys.argv) > 1:
    applications = sys.argv[1:]
    find_equivalents = True
else:
    ptab_patents = { d['respondentPatentNumber'] for d in ptab.decisions()
            if 'respondentPatentNumber' in d}
    if generics:
        app_tuples = { row.app_tuple for row in ob.all_patents
                if row['patent_no'] in ptab_patents }
        print("Got patent-associated applications")
        form_tuples = { r.form_tuple for r in ob.product_recs(app_tuples) }
        print("Got drug forms")
        applications = { r['appl_no']
                for r in ob.generics_for_formulations(form_tuples) }
        print("Got generic applications")
    else:
        applications = { row['appl_no'] for row in ob.all_patents
                if row['patent_no'] in ptab_patents }

print(f"{len(applications)} applications found.")

for appno in applications:
    print(f"Application {appno}:")
    ob_tuples = { prod.form_tuple
            for prod in ob.all_products if prod['appl_no'] == appno }
    ndc_tuples = { ndc.form_tuple(r) for r in ndc.recs_for_appno(appno) }

    if find_equivalents:
        for ot in ob_tuples:
            for nt in mno.find_equivalents(ot, ndc_tuples):
                print(f"  OB match: {ot}, {nt}")

    if find_nonequivalents:
        ob_ne_tuples, ndc_ne_tuples = mno.only_nonequivalents(ob_tuples,
                ndc_tuples)
        if len(ndc_ne_tuples) > 0:
            for tup in ob_ne_tuples: print("  OB: " + str(tup))
            for tup in ndc_ne_tuples: print(" NDC: " + str(tup))
