#!/usr/bin/env python3

def aggregate(iterable, proc, proc2 = None, postproc = None):
    """
        For each item in iterable, executes proc on it and indexes based on the
        result. The output is a dict mapping index values to lists of elements
        from the iterable.

        Optionally, if proc2 is given, iterable values are first converted using
        that proc. If postproc is given, then the lists of elements are
        transformed using that postproc.
    """
    res = {}
    for item in iterable:
        val = item if proc2 is None else proc2(item)
        res.setdefault(proc(item), []).append(val)
    if postproc is not None:
        res = { key: postproc(val) for key, val in res.items() }
    return res

def aggregate_multi(iterable, proc):
    """
        For each item in iterable, executes proc on it to receive a list of
        index values. The result is a dict mapping each index value to a list of
        items that produced that index value as one of its proc results.
    """
    res = {}
    for item in iterable:
        for idx in proc(item):
            res.setdefault(idx, []).append(item)
    return res

def histogram(data, interval, offset = 0, frac = False):
    if frac:
        postproc = lambda x: len(x) / len(data)
    else:
        postproc = lambda x: len(x)
    return sorted(aggregate(
        [
            round((elt - offset) / interval) * interval + offset
            for elt in data
        ],
        lambda x: x,
        postproc = postproc
    ).items())

class Table:
    def __init__(self, data):
        self.data = data
        self.indexes = {}
        self.procs = {}
        self.multi_procs = {}

    def index(self, idx_name, func = None):
        """
            Creates an index on the table called idx_name. The value to be
            indexed will be the result of executing func on each row of the
            table. If no func is given, it will default to
            lambda row: row[idx_name].
        """
        if func is None: func = lambda x: x[idx_name]
        self.indexes[idx_name] = aggregate(self.data, func)
        self.procs[idx_name] = func

    def index_multi(self, idx_name, func):
        """
            As with index(), creates an index named idx_name, indexing the
            elements of the table based on the output of func. However, func
            should return a list of items rather than a single item for
            indexing.
        """
        self.indexes[idx_name] = aggregate_multi(self.data, func)
        self.multi_procs[idx_name] = func

    def append(self, row):
        """
            Adds a row to the data table and indexes it.
        """
        self.data.append(row)
        for idx_name, proc in self.procs.items():
            self.indexes[idx_name].setdefault(proc(row), []).append(row)
        for idx_name, proc in self.multi_procs.items():
            for item in proc(row):
                self.indexes[idx_name].setdefault(item, []).append(row)

    def get(self, idx_name, value):
        """
            Retrieves table rows based on the index named idx_name matching
            value. If no rows exists, returns an empty list.
        """
        return self.indexes[idx_name].get(value, [])

    def has(self, idx_name, value):
        """
            Tests whether the table has the given value under the index named
            idx_name.
        """
        return value in self.indexes[idx_name]

    def get_multi(self, idx_name, values):
        """
            Finds rows matching any of the given values and returns a flattened
            list of those rows.
        """
        return [ row for v in values for row in self.get(idx_name, v) ]

    def indexed_values(self, idx_name):
        """
            An iterator that, for the given index name, yields for each indexed
            value.
        """
        return self.indexes[idx_name].keys()

    def apply(self, idx_name, func):
        """
            For each indexed value, applies func to the list of records matching
            that indexed value. Returns a dict mapping indexed values to outputs
            of the func.
        """
        return {
            k: func(self.get(idx_name, k))
            for k in self.indexed_values(idx_name)
        }

    def __iter__(self):
        return iter(self.data)

    def __getitem__(self, key):
        return self.data[key]

    def __len__(self):
        return len(self.data)


class Matrix:

    """
        A matrix of data with a common set of headers.
    """

    def __init__(self, headers, name_header = ''):
        self.headers = list(headers)
        self.rows = []
        self.lens = [ len(name_header), *[ len(str(h)) for h in headers ] ]
        self.name_header = name_header

    def add(self, name, row):
        """
            Adds a row of data to the matrix. The row should be a dict mapping
            at least some header names to data values for the row.
        """
        if type(row) == dict:
            new_row = [
                str(name), *[ str(row.get(h, '')) for h in self.headers ]
            ]
        else:
            new_row = [
                str(name), *[ str(elt) for elt in row ]
            ]
            assert(len(new_row) == len(self.headers) + 1)

        self.rows.append(new_row)
        self.lens = [
            max(len(new_elt), old_len)
            for new_elt, old_len in zip(new_row, self.lens)
        ]

    def print(self, **args):
        all_heads = [ self.name_header, *[ str(h) for h in self.headers ] ]
        print(
            " ".join(h.ljust(l) for h, l in zip(all_heads, self.lens)),
            **args
        )
        for row in self.rows:
            print(
                " ".join(h.ljust(l) for h, l in zip(row, self.lens)),
                **args
            )

    def __iter__(self):
        yield([ self.name_header ] + self.headers)
        for row in self.rows: yield(row)

    def col(self, header):
        idx = self.headers.index(header) + 1
        return [ r[idx] for r in self.rows ]

    @classmethod
    def from_dicts(cls, d):
        res = cls(sorted({ vk for v in d.values() for vk in v.keys() }))
        for name, vals in d.items():
            res.add(name, vals)
        return res
