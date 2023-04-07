#!/usr/bin/env python3

import ob
import analysis
import nadac
import ptab
import datetime

def cafc_groups():
    """
        Groups every relevant CAFC decision by CAFC and PTAB disposition.
    """
    decisions = analysis.ob_ptab_decisions();
    decisions.index_multi(
        'appeal',
        lambda d: [ appeal['uniqueid'] for appeal in d['appeals'] ]
    )

    appeals = agg.Table({
        ap for ap in ptab.cafc_decisions()
        if ap['uniqueid'] in decisions.indexed_values('appeal')
    })
    appeals.index(
        'disp_cat',
        lambda a: (
            a['dispgeneral'],
            *{
                o
                for d in decisions.get('appeal', a['uniqueid'])
                for o in ptab.decision_orders(d, filtered = True)
            }
        )
    )

    for cat in appeals.indexed_values('disp_cat'):
        yield(cat, appeals.get('disp_cat', cat))


def appeal_group_tex_report(io = sys.stdout):
    """
        Emits a TeX report based on cafc_groups() for each appeal in its
        appropriate category.
    """
    for cat, appeals in cafc_groups():
        print("\n\n\\subsection{*****}", file = io)
        print(f"% {cat}", file = io)
        for a in appeals:
            appeal_tex_report(a, io)

def appeal_tex_report(appeal, io = sys.stdout):
    decs = ptab.decisions().get_multi('proc', appeal['orig_trib_dockets'])
    name = re.sub(r" \[.*\]$", "", appeal['casename'])
    print(
        f"\n{name}\n{appeal['print_name']} ({appeal['docdate']})\n"
        f"% {appeal['dispgeneral']}, "
        f"{appeal['precedentialstatus']} ({appeal['uniqueid']})\n"
        f"% {appeal['url']}",
        file = io
    )
    print(f"%  PTAB decisions: {len(decs)}", file = io)
    for d in decs:
        print(
            f"%    {d['proceedingNumber']} ({d['decisionDate']}): "
            f"{', '.join(ptab.decision_orders(d, filtered = True))}",
            file = io
        )

    eqs = {
        eq
        for d in decs
        for eq in ob.eqs_for_patent(d['respondentPatentNumber'])
    }
    print(
        f"%  Equivalence classes: {len(eqs)} "
        f"({'; '.join([ str(e.eq_id) for e in eqs ])})",
        file = io
    )
    ingredients = sorted({ eq.one_form_tuple().ingredient for eq in eqs })
    print(f"%  Ingredients: {'; '.join(ingredients)}", file = io)



def best_prices(ndcs):
    interval = datetime.timedelta(days = 30)
    num_intervals = 110
    start_date = datetime.date(2014, 1, 1)

    res = []
    for i in range(0, num_intervals):
        date = start_date + interval * i
        price = nadac.best_price(ndcs, date - interval, date)
        if price is not None:
            res.append((date, price))

    return res

first_use = True

def eq_class_tex_graph(eq_class, with_ptab = True):
    global first_use

    """
        Produces TeX pgfplots code for a graph of an equivalence class.
    """
    if type(eq_class) is int: eq_class = ob.EquivalenceClass.get(eq_class)

    ndcs = { rec['ndc'] for rec in analysis.ndc_records_for_ob_forms(eq_class) }
    prices = best_prices(ndcs)
    decisions = ptab.decisions_for_patents(ob.patents_for_eq_class(eq_class))
    dates = {
        ('Fed.~Cir.', a['docdate'])
        for d in decisions
        for a in d['appeals']
    }
    if with_ptab:
        dates.update({
            ('PTAB', ptab.decision_date(d).isoformat())
            for d in decisions
            if 'appeals' in d
        })

    years = [ f"{y}-01-01" for y in range(2014, 2023) ]

    form_tuple = eq_class.one_form_tuple()
    strength = form_tuple.strength.lower().split('; ')[0]
    strength = strength.removeprefix("eq ").removesuffix(' base').replace(
        '%', '\\%'
    )

    print("\\begin{figure}[H]\n\\begin{center}")
    print("\\begin{tikzpicture}")
    #print("\\pgfplotsset{set layers}")

    print("\\begin{axis}[")
    print("    drugpricegraph,")
    print(
        "    title={" +
        form_tuple.ingredient.capitalize().split('; ')[0] + ", " + strength
          + "},"
    )
    print("    xtick={" + ",".join(years) + "},")
    print(
        "    extra x ticks={" + ",".join([ d for t, d in dates ]) + "},"
    )
    print(
        "    extra x tick labels={" + ",".join([ t for t, d in dates ]) + "},"
    )
    print("]")
    print("\\addplot coordinates {")
    for date, price in prices:
        print(f"    ({date}, {price})")
    print("};")
    print("\\end{axis}")

    print("\\begin{axis}[drugprodgraph]")
    print("\\addplot coordinates {")
    yp = analysis.yearly_products(eq_class, start=2014, end=2023)
    for year, prod in yp.items():
        print(f"    ({year}-01-01, {prod})")
    print("};")
    print("\\end{axis}")

    print("\\end{tikzpicture}\n\\end{center}")
    print( "\\caption{%")
    print("Unit price of " +
        form_tuple.ingredient.lower().split('; ')[0] +
        ", " + strength + "."
    )
    if first_use:
        first_use = False
        print(
            "The line shows the lowest price for the drug formulation " + \
            "in the previous 30-day period, as reflected in NADAC data."
        )
        print(
            "The bars show the number of products listed in the NDC " + \
            "directory for the formulation."
        )
    if not with_ptab:
        print("Dates of PTAB decisions omitted.")
    print("}")
    print("\\end{figure}\n")

def tex_heading(text):
    print()
    print("\\clearpage")
    print("\\begin{center}")
    print("\\textbf{" + text + "}")
    print("\\end{center}")
    print()


if __name__ == "__main__":
    tex_heading("III.A, Affirmances of Unpatentability")

    eq_class_tex_graph(7771)
    eq_class_tex_graph(6627, with_ptab = False)
    eq_class_tex_graph(2385)

    tex_heading("III.A.1, Rivastigmine")
    eq_class_tex_graph(6230)

    tex_heading("III.A.2, Buprenorphine")
    eq_class_tex_graph(1005, with_ptab = False)

    tex_heading("III.A.3, Abiraterone")
    eq_class_tex_graph(5)

    tex_heading("III.A.5, Prasugrel")
    eq_class_tex_graph(5870)

    tex_heading("III.A.6, Glatiramer")
    eq_class_tex_graph(7718, with_ptab = False)

