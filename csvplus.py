#!/usr/bin/env python3

import csv

class Reader:

    def __init__(self, *args, **params):
        self.reader = csv.reader(*args, **params)
        self.header = None
        self.header_proc = None

    def __iter__(self):
        return self

    def __next__(self):
        if self.header is None:
            h = next(self.reader)
            if self.header_proc is not None:
                h = [ self.header_proc(x) for x in h ]
            self.header = { h[i]: i for i in range(0, len(h)) }

        row = next(self.reader)
        return Row(self.header, row)

class Row:
    def __init__(self, header, row):
        self.header = header
        self.row = row

    def __getitem__(self, key):
        if type(key) is str:
            return self.row[self.header[key]]
        elif type(key) is int:
            return self.row[key]
        else:
            raise TypeError("Invalid key")

    def __repr__(self):
        return str({ k: self.row[v] for k, v in self.header.items() })
    def __str__(self):
        return str({ k: self.row[v] for k, v in self.header.items() })

    def __setitem__(self, key, value):
        self.row.extend([ None ] * (len(self.header) - len(self.row)))
        if key in self.header:
            self.row[self.header[key]] = value
        else:
            self.header[key] = len(self.row)
            self.row.append(value)


class UniqueRowWriter:
    """
        Creates and writes to a CSV file, with the rule that only unique rows
        can be written.
    """
    def __init__(self, file):
        self.file = file
        self.cache = set()
        self.header = None

    def __enter__(self):
        self.io = open(self.file, "w", newline = '')
        self.writer = csv.writer(
            self.io, dialect = "unix", quoting = csv.QUOTE_MINIMAL
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.io.close()

    def write_header(self, header):
        self.writer.writerow(header)
        self.header = header

    def writerow(self, row):
        assert self.header is not None
        assert len(row) == len(self.header)
        if type(row) is not tuple: row = tuple(row)
        if row not in self.cache:
            self.cache.add(row)
            self.writer.writerow(row)

