#!/usr/bin/env python3

import analysis
import tex
import ob
import ptab
import agg
import statistics

tex.to_file('rsi-data.tex')

tex.cmd('ptab-count', len(ptab.decisions()))

# Number of patents in PTAB trials.
tex.cmd('ptab-patents', len(ptab.decisions().indexed_values('patent_no')))

# Number of Orange Book patents.
tex.cmd('ob-patents', len(ob.all_patents.indexed_values('patent_no')))

# Number of Orange Book products.
tex.cmd('ob-products', len(ob.all_products.indexed_values('app_tuple')))

# Number of FDA applications in the Orange Book.
tex.cmd('ob-apps', len({
    at.appl_no for at in ob.all_products.indexed_values('app_tuple')
}))

# Number of OB patents litigated at PTAB.
tex.cmd('ob-ptab-patents', len(
    analysis.ob_ptab_decisions().indexed_values('patent_no')
))

# Number of OB products (by application tuples) covered by a PTAB-litigated
# patent.
tex.cmd(
    'ob-ptab-products',
    len(analysis.ptab_app_tuples())
)

# Number of PTAB proceedings on OB patents.
tex.cmd('ob-ptab-proceedings', len(analysis.ob_ptab_decisions()))

tex.cmd('invalid-pats', len({
    d['respondentPatentNumber']
    for d in analysis.ob_ptab_decisions().get('outcome', 'unpatentable')
}))

tex.pct('invalid-pct', tex.get('invalid-pats') / tex.get('ob-ptab-patents'))

# PTAB decisions by disposition and year.
tex.tbl('ob-ptab-by-year', agg.Matrix.from_dicts(
    analysis.ob_ptab_decisions().apply(
        'outcome',
        lambda x: {
            y: len([d for d in x if d['decisionDate'][-4:] == str(y)])
            for y in range(2013, 2023)
        }
    )
))

tex.cmd('prods-with-unlitigated-pats', sum(
    1
    for data in analysis.ptab_app_tuples().values()
    if 'unlitigated' in data
))

tex.frac('unlitigated-prod-frac', 'prods-with-unlitigated-pats',
    'ob-ptab-products')

# Number of formulation equivalence classes
tex.cmd('ob-eqs', len(ob.EquivalenceClass.all()))

# Formulation equivalence classes with at least one patent.
tex.cmd('ob-pat-eqs', len(ob.eq_classes_with_patent()))

tex.cmd('ob-ptab-eqs', len(analysis.ptab_equivalence_classes()))

tex.pct('ob-pct-generic', statistics.mean(
    1 if ob.is_a_rated(at) else 0
    for at in ob.all_products.indexed_values('app_tuple')
))

tex.tbl('prods-per-eq', analysis.products_per_equivalence_class())

tex.coords(
    'generic-approvals-after-ptab',
    analysis.generic_approvals_after_ptab(
        analysis.ob_ptab_decisions(), years = range(1, 8)
    ),
    legend = 'After PTAB decision'
)

tex.coords(
    'generic-approvals-after-nda',
    analysis.generic_approvals_after_control(
        years = range(1, 20), mean_ptab_time = 0,
    ),
    legend = 'After NDA approval'
)

tex.cmd('avg-ptab-years', tex.mean(
    [ t / 365 for t in analysis.approval_to_decision_time() ]
))

tex.cmd(
    'eq-class-date-pairs',
    len(analysis.equivalence_class_ptab_date_pairs(
        analysis.ob_ptab_decisions()
    ))
)

tex.cmd(
    'forms-with-3-yr-price',
    len(analysis.ptab_price_change(analysis.ob_ptab_decisions(), years = 3))
)

tex.cmd(
    'forms-with-5-yr-price',
    len(analysis.ptab_price_change(analysis.ob_ptab_decisions(), years = 5))
)

tex.coords(
    'price-trend-ptab-q',
    zip(
        [ i / 4 for i in range(0, 22) ],
        analysis.ptab_decision_price_trends(analysis.ob_ptab_decisions())
    ),
    legend = 'PTAB challenged'
)
tex.coords(
    'price-trend-unpatentable-q',
    zip(
        [ i / 4 for i in range(0, 22) ],
        analysis.ptab_decision_price_trends(
            analysis.ob_ptab_decisions().get('outcome', 'unpatentable')
        )
    ),
    legend = 'Held unpatentable'
)

tex.coords(
    'price-trend-not-unpatentable-q',
    zip(
        [ i / 4 for i in range(0, 22) ],
        analysis.ptab_decision_price_trends(
            analysis.ob_ptab_decisions().get('outcome', 'not unpatentable')
        )
    ),
    legend = 'Not unpatentable'
)

tex.pct('5-yr-ptab-price-change', 1 - statistics.mean(
    analysis.ptab_price_change(
        analysis.ob_ptab_decisions(), years = 5
    )
))
tex.pct('5-yr-unpat-price-change', 1 - statistics.mean(
    analysis.ptab_price_change(
        analysis.ob_ptab_decisions().get('outcome', 'unpatentable'), years = 5
    )
))
tex.pct('5-yr-not-unpat-price-change', 1 - statistics.mean(
    analysis.ptab_price_change(
        analysis.ob_ptab_decisions().get('outcome', 'not unpatentable'),
        years = 5
    )
))

tex.coords('3-yr-unpat-price-hist', agg.histogram(
    analysis.ptab_price_change(
        analysis.ob_ptab_decisions().get('outcome', 'unpatentable'),
        years = 3, zero = True
    ),
    0.25, offset = 0.125, frac = True
))

tex.pct('3-yr-unpat-price-25pct', statistics.mean([
    1 if x <= 0.25 else 0
    for x in analysis.ptab_price_change(
        analysis.ob_ptab_decisions().get('outcome', 'unpatentable'), years = 3
    )
]))

tex.pct('3-yr-unpat-price-125pct', statistics.mean([
    1 if x >= 1.25 else 0
    for x in analysis.ptab_price_change(
        analysis.ob_ptab_decisions().get('outcome', 'unpatentable'), years = 3
    )
]))

tex.coords('3-yr-not-unpat-price-hist', agg.histogram(
    analysis.ptab_price_change(
        analysis.ob_ptab_decisions().get('outcome', 'not unpatentable'),
        years = 3, zero = True
    ),
    0.25, offset = 0.125, frac = True
))

