# Orange Book Patent Analysis Programs

*Charles Duan, April 7, 2023*


This is a set of programs that I use for analysis of drug patents, drug pricing,
and PTAB trials. Among other things, it was the basis of my study
[*Administrative Patent Challenges and Drug
Prices*](https://www.rstreet.org/wp-content/uploads/2022/09/FINAL_264.pdf).


## Data Sources

Since many of the data sources are too large to include in the repository, you
will have to obtain them yourself. They are all publicly available and should be
accessible online without charge.

The following sections give the name of directories or files in which data
should be placed, describing where to get the data and how to name it.

### `ptab.json`

This file contains relevant data on PTAB decisions. The `ptab.py` script
contains a function `get_decisions` which will generate the file.


### `cafc.csv`

This file, already included in the repository, contains records of Federal
Circuit decisions based on Jason Rantanen's [*Compendium of Federal Circuit
Decisions*](https://empirical.law.uiowa.edu/compendium-federal-circuit-decisions).
I added one record to the end that was missing. The file includes only columns
that were relevant to my analysis.


### `obdata`

This folder should contain the FDA's datasets of Orange Book data. The current
Orange Book data is available on [this
website](https://www.fda.gov/drugs/drug-approvals-and-databases/orange-book-data-files).
You will also need historical files, since the FDA deletes outdated records. The
[Internet Archive](https://www.archive.org) remarkably has downloaded the FDA's
ZIP files over time, so you can simply retrieve archived versions of the
aforementioned page.

Prior to 2018, the data files were linked from [this page](https://web.archive.org/web/*/https://www.fda.gov/Drugs/InformationOnDrugs/ucm129689.htm).
After then, use [this page](https://web.archive.org/web/20200601000000*/https://www.fda.gov/drugs/drug-approvals-and-databases/orange-book-data-files).

The folder names within the `obdata` directory are generally based on the
original filenames with `.zip` removed, except for the 2013 folder which was
originally `EOBZIP_2013_07_08-30_Fixed_PE`.


### `ndc`

This folder should contain the FDA's National Drug Code Directory data. Current
data is on [this
page](https://www.fda.gov/drugs/drug-approvals-and-databases/national-drug-code-directory),
with the NDC database file linked at the bottom (use the Text version). Again,
because the FDA deletes outdated records, archived copies of the database are
needed, from the Internet Archive, with different links
[before](https://web.archive.org/web/20230000000000*/https://www.fda.gov/Drugs/InformationOnDrugs/ucm142438.htm)
and [after
2018](https://web.archive.org/web/20230000000000*/https://www.fda.gov/drugs/drug-approvals-and-databases/national-drug-code-directory).

The entries in the `ndc` directories should be subdirectories named
`ndc-`[date], and each subdirectory should contain the files `product.txt` and
`package.txt` (though only the former is used).


### `nadac`

The National Average Drug Acquisition Cost database files can be downloaded from
[this Medicaid page](https://data.medicaid.gov/nadac). The files, one for each
year, should be put in the `nadac` directory.


## Summarizing Data

Most of the scripts contain an initial function that summarizes a relevant
dataset for faster processing. The `summarize_records` function in `ndc.py` does
this, for example. These functions will leave behind a summarized dataset that
other functions in the scripts will use.

## Keying Records

Probably the most significant difficulty of working with these datasets is
matching records. There are two main unique entities.

### Formulations

A formulation represents a specific approved composition of a therapeutic, and
is uniquely identified by three elements: the active ingredients, the strengths
of each ingredient (usually, the mass per dose of the active ingredient), and
the route of administration. The FDA appears to use these three elements for
organizing the Orange Book and for determining therapeutic equivalents therein.

Unfortunately, the FDA is not always consistent with its naming schemes for
formulations across Orange Book editions. For example, where a drug includes
several active ingredients, the ingredients are not always listed in the same
order. As a result, the `ob.py` script automatically computes ``equivalence
classes`` that join together differently-named formulations that ought to be
treated as a single unit. Equivalence classes are each assigned a unique number
that can be used in various scripts as an identifier.

### Products

A product is a formulation made by a specific manufacturer. In other words, for
a given formulation, there may be one product or many (depending essentially on
whether there are generics).

In the Orange Book, a product is uniquely identified by two elements: an FDA
drug application number, and a "product number" assigned by the FDA (since a
single application for approval can contain several formulations, typically
differing in strengths).

In the NDC and NADAC databases, however, products are identified by NDC numbers.
A single product may have multiple NDC numbers because, among other things, an
NDC is assigned to a specific packaged product and a manufacturer may make
different-sized packs. As a result, it is necessary to reconcile Orange Book
formulations with NDCs. The `match_ndc_ob.py` script relies on a variety of text
matching and other techniques to perform this reconciliation.



## Using the Scripts

The `analysis.py` script is a good starting point for the sorts of analyses that
are possible. The script contains two types of functions. Some of them provide
basic utilities for joining the datasets. Others produce text-based reports
which are helpful for exploring the data.

The `*_analysis.py` scripts contain the functions I have used for specific
research projects.


## Crediting

If you use these programs in published your research, please cite it as follows:

> Charles Duan, *Orange Book Patent Analysis Programs* (Apr. 7, 2023),
> https://github.com/charlesduan/orangebook


