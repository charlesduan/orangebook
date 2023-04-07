#!/usr/bin/env python3

"""
Produces TeX outputs for data values.
"""

import re
import sys
import statistics

values = {}

outfile = sys.stdout

def to_file(filename):
    """
        Sends output to the given file.
    """
    global outfile
    outfile = open(filename, 'w')

def get(name):
    return values[name]

def cmd(name, data):
    """
        Produces a data definition command using the given data identifier name.
    """
    if name in values:
        raise AssertionError(f"{name} already defined")

    values[name] = data
    print(f"\\setdata{{{name}}}{{{fmt(data)}}}", file = outfile)

def pct(name, data):
    """
        Formats data, assumed to be a fraction, as a percentage.
    """
    cmd(name, fmt(data * 100) + "\\%")

def frac(name, numerator, denominator):
    """
        Formats a fraction given a numerator value and a denominator value.
    """
    return pct(name, get(numerator) / get(denominator))

NUM_WORDS = """
    zero one two three four five six seven eight nine ten eleven 
    twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen
""".split()

def fmt(data):
    """
        Formats a value according to its type.
    """
    if type(data) is int:
        if data < 20:
            return NUM_WORDS[num]
        else:
            return f"{data:,}"
    elif type(data) is float:
        return f"{data:.1f}"
    else:
        return str(data)

def mean(data):
    """
        Computes a formatted mean for a list.
    """
    res = statistics.mean(data)
    if res >= 100:
        return f"{res:.1f}"
    else:
        return f"{res:.2f}"


def tbl(name, data):
    data = list(data)
    cols = len(data[0])
    spec = 'l|' + 'r' * (cols - 1)
    res = r"\begin{center}\begin{tabular}" f"{{{spec}}}\n"
    res += "&".join([ f"\\textbf{{{h}}}" if h != "" else h for h in data[0] ])
    res += "\\\\\n\\hline\n"
    for row in data[1:]:
        res += f"\\textbf{{{row[0]}}}&"
        res += "&".join(fmt(c) for c in row[1:]) + "\\\\\n"
    res += r"\end{tabular}\end{center}"
    cmd(name, res)

def coords(name, data, legend = None):
    if type(data) is dict: data = data.items()
    res = ''
    if legend is not None: res += f'\\addlegendentry{{{legend}}}'

    res += '\\addplot coordinates {\n'
    for row in data:
        res += f"({{{row[0]}}}, {row[1]})\n"
    res += '}'
    cmd(name, res)
