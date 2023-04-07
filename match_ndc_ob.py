#!/usr/bin/env python3

"""
    Matches Orange Book formulation tuples against an NDC formulation tuples.
"""

import re
import math
import ob
import ndc


def only_nonequivalents(ob_forms, ndc_forms):
    nonequiv_ob = { of for of in ob_forms
            if not any(find_equivalents(of, ndc_forms)) }
    nonequiv_ndc = { nf for nf in ndc_forms
            if all(not equivalent(of, nf) for of in ob_forms) }
    return [ nonequiv_ob, nonequiv_ndc ]

def find_equivalents(ob_form, ndc_forms):
    return filter(lambda x: equivalent(ob_form, x), ndc_forms)


def equivalent(ob_form, ndc_form):
    """
    Tests if an Orange Book listing is equivalent to an NDC listing. This looks
    at the form/route and the active ingredients/strengths.
    """
    if type(ob_form) is ob.FormulationTuple:
        if not equivalent_form(ob_form.form_route, ndc_form.form_route):
            return False
        if not equivalent_composition(comp_map(ob_form), comp_map(ndc_form)):
            return False
        return True
    elif type(ob_form) is ob.EquivalenceClass:
        return any([ equivalent(ft, ndc_form) for ft in ob_form.form_tuples ])
    else:
        raise TypeError("Invalid ob_form type")

def comp_map(tup):
    elements = (tup.ingredient, *tup[2:])
    return list(zip(*(map(lambda y: y.strip(), x.split(';'))
        for x in elements)))

def equivalent_form(ob_fr, ndc_fr):
    """
    Tests if the form and route are equivalent between an Orange Book listing
    and an NDC listing.
    """
    ob_form, ob_route = map(form_route_words, ob_fr.split(';', 1))
    ndc_form, ndc_route = map(form_route_words, ndc_fr.split(';', 1))

    if "INJECTION" in ob_route and "INJECTION" in ndc_route: return True
    if "INJECTION" in ob_route and "INJECTION" in ndc_form: return True
    if "INHALATION" in ob_route and "INHALATION" in ndc_form: return True
    if 0 == len(ob_route & ndc_route): return False
    if 0 == len(ob_form & ndc_form): return False
    return True

form_route_map = {
        "IV": "INJECTION",
        "INTRAVENOUS": "INJECTION",
        "INJECTABLE": "INJECTION",
        "SC": "SUBCUTANEOUS",
        "PELLETS": "PELLET",
        "INHALANT": "INHALATION",
        "CAPSULE": "TABLET",
        "FILM": "PATCH",
        "LIQUID": "SOLUTION",
}

def form_route_words(text):
    return { form_route_map.get(x, x) for x in re.findall(r"\w+", text) }

def equivalent_composition(ob_comps, ndc_comps):
    # Hash OB ingredients
    ob_data = dict(ob_comps)
    for ing, strength, unit in ndc_comps:
        match_ing = match_ingredient(ing, ob_data)
        if match_ing is None: return False

        # Special case for tavaborole
        if match_ing == 'TAVABOROLE':
            if ob_data[match_ing] == '5%' and strength == '43.5':
                ob_data.pop(match_ing)
                continue
        if not equivalent_strength(ob_data.pop(match_ing),
                strength, unit): return False
    return (len(ob_data) == 0)

def match_ingredient(ing, ing_dict):
    words = ing.split(" ")
    matches = [ i.split(" ") for i in ing_dict.keys() ]
    for i in range(len(words)):
        matches = [ m for m in matches if len(m) > i and m[i] == words[i] ]
        if len(matches) == 1: return " ".join(matches[0])
        if len(matches) == 0: return None
    return None


num_re = r"(?:\d*\.)?\d+"
def equivalent_strength(ob_strength, ndc_strength, ndc_unit):
    if ob_strength is None: return False
    if m := re.search(num_re, ndc_unit):
        ndc_ratio = float(ndc_strength) / float(m.group(0))
    else:
        ndc_ratio = float(ndc_strength)
    ndc_num = float(ndc_strength)

    for number in re.finditer(r"(?<!/)" + num_re, ob_strength):
        number = number.group(0)
        if ndc_strength == number: return True
        num = float(number)
        if math.isclose(num, ndc_num): return True
        if num == ndc_ratio: return True
        if "GM" in ob_strength or "ug" in ndc_unit:
            # Possible unit conversions
            if math.isclose(num * 1000, ndc_ratio, rel_tol = 1e-4): return True
            if math.isclose(num * 1000, ndc_num, rel_tol = 1e-4): return True
        if ndc_unit.startswith('g/'):
            if math.isclose(num / 1000, ndc_num, rel_tol = 1e-4): return True
        if "%" in ob_strength:
            # Percentages are often mg/mL, so we divide the OB percentage by 100
            # and multiply it by 1000
            if math.isclose(num * 10, ndc_ratio, rel_tol = 1e-4): return True
            if math.isclose(num * 10, ndc_num, rel_tol = 1e-4): return True
    if m := re.match(f"^({num_re}).*/({num_re})", ob_strength):
        ob_ratio = float(m[1]) / float(m[2])
        if math.isclose(ob_ratio, ndc_ratio, rel_tol=1e-04): return True

    return False



def tests():
    assert "A" == match_ingredient("A", { "A": 1 })
    assert "A B" == match_ingredient("A", { "A B": 1 })
    assert "A B" == match_ingredient("A C", { "A B": 1 })
    assert "A C" == match_ingredient("A C", { "A B": 1, "A C": 2 })
    assert None is match_ingredient("A", { "A B": 1, "A C": 2 })
    assert "A B C" == match_ingredient("A B C", { "A B C": 1, "A B": 2 })

    assert equivalent_strength("EQ 6.3MG BASE", "6.3", "mg/1")
    assert equivalent_strength("EQ 1MG BASE", "1", "mg/1")
    assert equivalent(
            ob.FormulationTuple(
                'BUPRENORPHINE HYDROCHLORIDE; NALOXONE HYDROCHLORIDE',
                'FILM;BUCCAL', 'EQ 6.3MG BASE;EQ 1MG BASE'),
            ndc.FormulationTuple(
                'BUPRENORPHINE HYDROCHLORIDE; NALOXONE HYDROCHLORIDE DIHYDRATE',
                'FILM;BUCCAL', '6.3; 1', 'mg/1; mg/1'))

    assert equivalent_form("INJECTABLE;IV (INFUSION), SUBCUTANEOUS",
            "INJECTION, SOLUTION;INTRAVENOUS; SUBCUTANEOUS")

    assert equivalent_strength("0.7MG", ".7", "MG")

    assert equivalent(
            ob.FormulationTuple(
                'DEXMEDETOMIDINE HYDROCHLORIDE', 'INJECTABLE;INJECTION',
                'EQ 200MCG BASE/2ML (EQ 100MCG BASE/ML)'),
            ndc.FormulationTuple('DEXMEDETOMIDINE HYDROCHLORIDE',
                'INJECTION, SOLUTION, CONCENTRATE;INTRAVENOUS', '100', 'ug/mL'))

    assert not equivalent(
            ob.FormulationTuple('DEXMEDETOMIDINE HYDROCHLORIDE', 'INJECTABLE;INJECTION',
                'EQ 400MCG BASE/100ML (EQ 4MCG BASE/ML)'),
            ndc.FormulationTuple('DEXMEDETOMIDINE HYDROCHLORIDE',
            'INJECTION, SOLUTION, CONCENTRATE;INTRAVENOUS', '100', 'ug/mL'))
    assert equivalent_strength("0.004%", "0.04", "mg/mL")
    assert equivalent_strength("1GM", "1000", "mg")
    assert not equivalent_strength("1MG", "1000", "mg")
    assert equivalent_form("SOLUTION;INTRAVENOUS", "INJECTION;INTRAVENOUS")
    assert equivalent_strength('300 UNITS/3ML', '100', 'U/mL')
    assert equivalent_strength('0.07% ACID', '.7', 'mg/mL')
    assert equivalent_form("INJECTABLE;INJECTION",
            "INJECTION, SOLUTION;SUBCUTANEOUS")
    assert equivalent(
            ob.FormulationTuple('AZELASTINE HYDROCHLORIDE',
                'SPRAY, METERED;NASAL', '0.137MG/SPRAY'),
            ndc.FormulationTuple('AZELASTINE HYDROCHLORIDE', 'SPRAY;NASAL',
                '137', 'ug/.137mL'))
    assert equivalent(
            ob.FormulationTuple('MESALAMINE', 'CAPSULE, EXTENDED RELEASE;ORAL',
                '375MG'),
            ndc.FormulationTuple('MESALAMINE', 'CAPSULE, EXTENDED RELEASE;ORAL',
                '.375', 'g/1'))

if __name__ == '__main__':
    tests()
