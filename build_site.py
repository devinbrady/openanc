"""
All steps necessary to build OpenANC pages
"""

import argparse

from scripts.refresh_data import RefreshData
from scripts.build_index import BuildIndex
from scripts.build_districts import BuildDistricts
from scripts.build_ancs import BuildANCs
from scripts.build_wards import BuildWards


parser = argparse.ArgumentParser()
parser.add_argument('-r', '--refresh-data', action='store_true', help='Refresh local CSVs from Google Sheets')
parser.add_argument('-i', '--build-index', action='store_true', help='Build index and other top-level pages')
parser.add_argument('-w', '--build-wards', action='store_true', help='Build page for each Ward')
parser.add_argument('-a', '--build-ancs', action='store_true', help='Build page for each ANC')
parser.add_argument('-d', '--build-districts', action='store_true', help='Build page for each SMD')

args = parser.parse_args()


if args.refresh_data:
    r = RefreshData()
    r.run()

if args.build_index:
    bi = BuildIndex()
    bi.run()

if args.build_wards:
    bw = BuildWards()
    bw.run()

if args.build_ancs:
    ba = BuildANCs()
    ba.run()

if args.build_districts:
    bd = BuildDistricts()
    bd.run()
