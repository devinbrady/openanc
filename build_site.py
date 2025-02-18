"""
All steps necessary to build OpenANC pages
"""

import os
import sys
import argparse
from datetime import datetime

from scripts.refresh_data import RefreshData
from scripts.process_candidates import ProcessCandidates
# from scripts.process_election_results import ProcessElectionResults
from scripts.index import BuildIndex
from scripts.districts import BuildDistricts
from scripts.ancs import BuildANCs
from scripts.wards import BuildWards
from scripts.people import BuildPeople
from tests.validate_links import ValidateLinks

start_time = datetime.now()

parser = argparse.ArgumentParser()
parser.add_argument('-r', '--refresh-data', action='store_true', help='Refresh local CSVs from Google Sheets')
parser.add_argument('-f', '--full-refresh-data', action='store_true', help='Download every Google Sheet from OpenANC Source, not just the frequently updated ones. Use in addition to --refresh-data')
parser.add_argument('-c', '--candidates', action='store_true', help='Process list of candidates from DCBOE')
parser.add_argument('-i', '--build-index', action='store_true', help='Build index and other top-level pages')
parser.add_argument('-w', '--build-wards', action='store_true', help='Build page for each Ward')
parser.add_argument('-a', '--build-ancs', action='store_true', help='Build page for each ANC')
parser.add_argument('-d', '--build-districts', action='store_true', help='Build page for each SMD')
parser.add_argument('-p', '--build-people', action='store_true', help='Build page for each person')
parser.add_argument('-v', '--validate-links', action='store_true', help='Confirm internal link validity')
parser.add_argument('-e', '--election-results', action='store_true', help='Process election results from DCBOE')
parser.add_argument('--all', action='store_true', help='Run all site-building steps')

args = parser.parse_args()


# Make directories if they don't already exist
# os.makedirs('/docs/map_2012/ancs/districts', exist_ok=True)


if args.all:
    """
    These steps are all needed to do a rebuild of the site from the information in "OpenANC Source" google sheets.

    The only steps left out are ProcessCandidates and ProcessElectionResults, which only need to be run
    when the underlying data changes.
    """

    args.refresh_data = True
    args.build_index = True
    args.build_wards = True
    args.build_ancs = True
    args.build_districts = True
    args.build_people = True
    args.validate_links = True


# todo: maybe put the refresh_data step after both of the process_ ones?
if args.refresh_data:
    r = RefreshData()
    r.run(args.full_refresh_data)

# if args.candidates:
#     pc = ProcessCandidates()
#     pc.run()

# if args.election_results:
#     er = ProcessElectionResults()
#     er.run()

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

if args.validate_links:
    tl = ValidateLinks()
    tl.validate_internal_links()



if len(sys.argv) == 1:
    print('No arguments provided to build_site script, exiting.')

else:
    end_time = datetime.now()

    time_elapsed = end_time - start_time
    seconds_elapsed = time_elapsed.total_seconds()
    print(f'build_site: {seconds_elapsed:.1f} seconds')
