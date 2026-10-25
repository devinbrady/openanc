"""
Convert DCBOE candidate list PDFs to the CSVs in data/dcboe/excel-clean.

Run from the repo root with the webapp venv (pip install -r webapp/requirements-dev.txt):

    webapp/.venv/bin/python scripts/dcboe_pdf_to_csv.py links
    webapp/.venv/bin/python scripts/dcboe_pdf_to_csv.py ballot path/to/CANDIDATES.pdf
    webapp/.venv/bin/python scripts/dcboe_pdf_to_csv.py write-in path/to/WRITE-IN-CANDIDATES.pdf

The output filename defaults to the PDF's creation date, e.g. dcboe-write-in-2026-10-23.csv.
"""

import re
import csv
import argparse
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin

import requests
import pdfplumber
from bs4 import BeautifulSoup


ELECTIONS_URL = 'https://dcboe.org/elections/2026-elections'
OUTPUT_DIR = Path('data/dcboe/excel-clean')

LINK_TEXTS = {
    'ballot': 'Advisory Neighborhood Commission (ANC) Candidates in Ballot Order',
    'write-in': 'List of General Election Write-in Candidates',
}

BALLOT_COLUMNS = ['ANC-SMD', 'Name', 'Date of Pick-up', 'Date Filed', 'Date of Withdrawal', 'Challenge Notes']
WRITE_IN_COLUMNS = ['Office', 'Name', 'Date of Withdrawal']

WITHDREW_RE = re.compile(r'\(\s*withdrew\s*(.*?)\s*\)', re.IGNORECASE)
CHALLENGE_RE = re.compile(r'\(\s*(challenge.*?)\s*\)', re.IGNORECASE)

# Older write-in lists spelled out the office (with typos) instead of "ANC 1A01"
OFFICE_RE = re.compile(r'^(ANC|Advisory Neighbo\w* Commis+ioner)\s*', re.IGNORECASE)


def clean(cell):
    return ' '.join((cell or '').split())


def pdf_rows(pdf_path):
    """All table rows across every page, with each cell's whitespace collapsed."""
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                rows += [[clean(c) for c in row] for row in table]
    return rows


def pdf_created(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        raw = pdf.metadata.get('CreationDate', '')
    return datetime.strptime(raw[2:10], '%Y%m%d').date()


def split_name(name):
    """Pull "(withdrew 10/22/26)" and "(Challenge ...)" notes out of a candidate's name."""
    withdrew = WITHDREW_RE.search(name)
    challenge = CHALLENGE_RE.search(name)
    name = CHALLENGE_RE.sub('', WITHDREW_RE.sub('', name)).replace('*', '').strip()
    return name, (withdrew.group(1) if withdrew else ''), (challenge.group(1) if challenge else '')


def ballot_rows(pdf_path):
    rows = pdf_rows(pdf_path)
    header = next(r for r in rows if r and r[0] == 'ANC-SMD')
    # "Date of Pick-\nup" comes out of the PDF as "Date of Pick- up"
    col = {h.replace('- ', '-'): i for i, h in enumerate(header)}

    output = []
    for r in rows:
        if r == header or not r[col['Name']] or r[col['Name']].lower() == 'write-in, if any':
            continue
        name, withdrew, challenge = split_name(r[col['Name']])
        output.append([r[col['ANC-SMD']], name, r[col['Date of Pick-up']], r[col['Date Filed']], withdrew, challenge])
    return output


def write_in_rows(pdf_path):
    output = []
    for r in pdf_rows(pdf_path):
        if len(r) < 2 or not OFFICE_RE.match(r[1]):
            continue
        name, withdrew, _ = split_name(r[0])
        output.append([OFFICE_RE.sub('', r[1]).strip(), name, withdrew])
    return output


def current_links():
    """The PDF URL behind each link text on the DCBOE elections page."""
    soup = BeautifulSoup(requests.get(ELECTIONS_URL, timeout=30).text, 'html.parser')
    links = {}
    for a in soup.find_all('a', href=True):
        for kind, text in LINK_TEXTS.items():
            if clean(a.get_text()) == text:
                links[kind] = urljoin(ELECTIONS_URL, a['href'])
    return links


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('kind', choices=['links', 'ballot', 'write-in'])
    parser.add_argument('pdf', nargs='?', type=Path)
    parser.add_argument('-o', '--output', type=Path, help='Defaults to dcboe-<kind>-<PDF creation date>.csv')
    args = parser.parse_args()

    if args.kind == 'links':
        for kind, url in current_links().items():
            print(f'{kind}: {url}')
        return

    if not args.pdf:
        parser.error(f'{args.kind} needs a PDF path')

    if args.kind == 'ballot':
        columns, rows = BALLOT_COLUMNS, ballot_rows(args.pdf)
    else:
        columns, rows = WRITE_IN_COLUMNS, write_in_rows(args.pdf)

    output = args.output or OUTPUT_DIR / f'dcboe-{args.kind}-{pdf_created(args.pdf)}.csv'

    # CRLF to match the CSVs already in excel-clean
    with open(output, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, lineterminator='\r\n')
        writer.writerow(columns)
        writer.writerows(rows)

    print(f'input: {args.pdf.name}')
    print(f'{len(rows)} {args.kind} candidates, {sum(1 for r in rows if r[columns.index("Date of Withdrawal")])} withdrawn')
    print(f'output: {output}')


if __name__ == '__main__':
    main()
