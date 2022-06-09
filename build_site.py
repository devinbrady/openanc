"""
All steps necessary to build OpenANC pages
"""

import argparse
from datetime import datetime

from scripts.refresh_data import RefreshData
from scripts.index import BuildIndex
from scripts.districts import BuildDistricts
from scripts.ancs import BuildANCs
from scripts.wards import BuildWards
from scripts.people import BuildPeople

start_time = datetime.now()

parser = argparse.ArgumentParser()
parser.add_argument('-r', '--refresh-data', action='store_true', help='Refresh local CSVs from Google Sheets')
parser.add_argument('-i', '--build-index', action='store_true', help='Build index and other top-level pages')
parser.add_argument('-w', '--build-wards', action='store_true', help='Build page for each Ward')
parser.add_argument('-a', '--build-ancs', action='store_true', help='Build page for each ANC')
parser.add_argument('-d', '--build-districts', action='store_true', help='Build page for each SMD')
parser.add_argument('-p', '--build-people', action='store_true', help='Build page for each person')

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

if args.build_people:
    bp = BuildPeople()
    bp.run()


if not any([
        args.refresh_data
        , args.build_index
        , args.build_wards
        , args.build_ancs
        , args.build_districts
        , args.build_people
        ]):

    print('No arguments provided to build_site script, exiting.')

end_time = datetime.now()

time_elapsed = end_time - start_time
seconds_elapsed = time_elapsed.total_seconds()
print(f'build_site: {seconds_elapsed:.1f} seconds')