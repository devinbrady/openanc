"""Loads a DCBOE precinct-level results CSV (the "Election Night Unofficial Results" file and the
later unofficial / certified versions -- all share the same columns) into ElectionResult.

DCBOE republishes results several times while counting continues, so this is built to be run
again with each new file: rows are updated in place (simple-history records every vote change),
rows no longer in the file are removed, and a dry run (the default) prints what would change --
vote counts, leader changes, contests where no one has a first-choice majority.

Each named candidate is linked through PersonAlias (matching.resolve_person) and must resolve
to exactly one person who is a candidate for that district in this election. If any name
doesn't, nothing is written: add the missing alias or Candidate and run it again.

Vote counts are first-choice totals. The election-wide "Write-in" total becomes the
candidate-less row, as in earlier years. is_winner / is_write_in_winner are only set once the
results are certified; until then the first-ranked row is just "leading". Ranked-choice rounds
aren't part of this file and aren't imported here.

Save each DCBOE file under data/dcboe/election_results/ with the download date appended (DCBOE
reuses filenames), then:

  python manage.py import_election_results data/dcboe/election_results/<file>.csv \\
      --year 2026 --status election_night --as-of 2026-11-04
  python manage.py import_election_results ... --apply
"""
import csv
import datetime
import re
from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from simple_history.utils import update_change_reason

from directory.matching import add_alias, resolve_person
from directory.models import Candidate, District, Election, ElectionResult, PersonAlias

ANC_CONTEST_RE = re.compile(r'^ANC-(\S+)')
WRITE_IN = 'Write-in'
NOT_CANDIDATES = {'OVER VOTES', 'UNDER VOTES'}


class Command(BaseCommand):
    help = 'Import ANC results from a DCBOE results CSV (dry run unless --apply).'

    def add_arguments(self, parser):
        parser.add_argument('csv_path')
        parser.add_argument('--year', type=int, required=True)
        parser.add_argument('--status', required=True, choices=[
            Election.RESULTS_ELECTION_NIGHT, Election.RESULTS_UNOFFICIAL, Election.RESULTS_CERTIFIED,
        ])
        parser.add_argument('--as-of', required=True, type=datetime.date.fromisoformat, help='YYYY-MM-DD')
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        path = Path(options['csv_path'])
        try:
            election = Election.objects.get(year=options['year'])
        except Election.DoesNotExist:
            raise CommandError(f'No {options["year"]} election.')
        certified = options['status'] == Election.RESULTS_CERTIFIED

        totals, ballot_lines = self.read_contests(path)
        districts = self.districts_for(election)
        missing = sorted(set(districts) - set(totals))
        unknown = sorted(set(totals) - set(districts))
        if unknown:
            raise CommandError(f'Contests with no matching district: {", ".join(unknown)}')

        rows, errors = self.build_rows(election, districts, totals, certified)
        if errors:
            self.stderr.write(self.style.ERROR(f'{len(errors)} candidate name(s) could not be linked -- nothing written:'))
            for line in errors:
                self.stderr.write(f'  {line}')
            raise CommandError('Fix the names above (add an alias or Candidate) and run again.')

        self.report(election, rows, totals, ballot_lines, missing)

        if not options['apply']:
            self.stdout.write('\nDry run -- pass --apply to write.')
            return

        reason = f'DCBOE results file {path.name} ({options["status"]}, as of {options["as_of"]})'
        with transaction.atomic():
            kept = []
            for row in rows:
                result, _ = ElectionResult.objects.update_or_create(
                    election=election, district=row['district'], candidate=row['candidate'],
                    candidate_name_raw=row['candidate_name_raw'],
                    defaults={k: row[k] for k in ('votes', 'ranking', 'is_winner', 'is_write_in_winner', 'margin_of_victory')},
                )
                update_change_reason(result, reason)
                kept.append(result.pk)
                if row['candidate']:
                    add_alias(row['candidate'].person, row['candidate_name_raw'], PersonAlias.SOURCE_DCBOE_RESULTS,
                              note=f'{election.year} results, SMD {row["district"].designator}')
            stale = ElectionResult.objects.filter(election=election).exclude(pk__in=kept)
            removed = stale.count()
            stale.delete()

            election.results_status = options['status']
            election.results_as_of = options['as_of']
            election.results_source = path.name
            election.save()
        self.stdout.write(self.style.SUCCESS(f'Wrote {len(rows)} result row(s), removed {removed} stale row(s).'))

    def read_contests(self, path):
        """{designator: {candidate_name: votes}} summed over precincts, plus
        {designator: {'OVER VOTES': n, 'UNDER VOTES': n}}."""
        totals = defaultdict(lambda: defaultdict(int))
        ballot_lines = defaultdict(lambda: defaultdict(int))
        with path.open(encoding='utf-8-sig', newline='') as f:
            for row in csv.DictReader(f):
                match = ANC_CONTEST_RE.match(row['ContestName'].strip())
                if not match:
                    continue
                designator = match.group(1)
                name = ' '.join(row['Candidate'].split())
                votes = int(row['Votes'] or 0)
                if name in NOT_CANDIDATES:
                    ballot_lines[designator][name] += votes
                else:
                    totals[designator][name] += votes
        if not totals:
            raise CommandError(f'No ANC contests found in {path}.')
        return totals, ballot_lines

    def districts_for(self, election):
        """The districts this election was held in: the most recent redistricting cycle at or
        before the election year."""
        cycle = (
            District.objects.filter(redistricting_year__lte=election.year)
            .order_by('-redistricting_year').values_list('redistricting_year', flat=True).first()
        )
        return {d.designator: d for d in District.objects.filter(redistricting_year=cycle).select_related('ward')}

    def build_rows(self, election, districts, totals, certified):
        candidacies = {
            (c.district_id, c.person_id): c
            for c in Candidate.objects.filter(election=election).select_related('person')
        }
        rows, errors = [], []
        for designator, votes_by_name in sorted(totals.items()):
            district = districts[designator]
            ordered = sorted(votes_by_name.items(), key=lambda item: (-item[1], item[0] == WRITE_IN, item[0]))
            contest = []
            for name, votes in ordered:
                candidate = None
                if name != WRITE_IN:
                    resolution = resolve_person(name, district=district, election=election)
                    candidate = candidacies.get((district.pk, resolution.person.pk)) if resolution.is_exact else None
                    if candidate is None:
                        people = ', '.join(f'{p.full_name} (#{p.pk})' for p in resolution.people) or 'no alias match'
                        errors.append(f'{designator}: "{name}" -- {resolution.status}; {people}')
                        continue
                contest.append({'district': district, 'candidate': candidate, 'candidate_name_raw': name, 'votes': votes})

            for ranking, row in enumerate(contest, start=1):
                row['ranking'] = ranking
                row['is_winner'] = certified and ranking == 1
                row['is_write_in_winner'] = row['is_winner'] and row['candidate'] is None
                if len(contest) == 1:
                    row['margin_of_victory'] = None
                elif ranking == 1:
                    row['margin_of_victory'] = row['votes'] - contest[1]['votes']
                else:
                    row['margin_of_victory'] = row['votes'] - contest[0]['votes']
            rows.extend(contest)
        return rows, errors

    def report(self, election, rows, totals, ballot_lines, missing):
        existing = {
            (r.district_id, r.candidate_id, r.candidate_name_raw): r
            for r in ElectionResult.objects.filter(election=election)
        }
        old_leaders = {r.district_id: r for r in existing.values() if r.ranking == 1}

        changed, new = [], 0
        for row in rows:
            key = (row['district'].pk, row['candidate'].pk if row['candidate'] else None, row['candidate_name_raw'])
            old = existing.pop(key, None)
            if old is None:
                new += 1
            elif old.votes != row['votes']:
                changed.append(f'  {row["district"].designator} {row["candidate_name_raw"]}: {old.votes:,} -> {row["votes"]:,}')

        leader_changes = []
        for row in rows:
            if row['ranking'] != 1:
                continue
            old = old_leaders.get(row['district'].pk)
            if old and (old.candidate_id, old.candidate_name_raw) != (row['candidate'].pk if row['candidate'] else None, row['candidate_name_raw']):
                leader_changes.append(f'  {row["district"].designator}: {old.candidate_name_raw} -> {row["candidate_name_raw"]}')

        no_majority = []
        for designator, votes_by_name in sorted(totals.items()):
            total = sum(votes_by_name.values())
            top = max(votes_by_name.values(), default=0)
            if total and len(votes_by_name) > 1 and top * 2 <= total:
                no_majority.append(f'{designator} (leader {top / total:.1%})')

        total_votes = sum(r['votes'] for r in rows)
        under = sum(lines.get('UNDER VOTES', 0) for lines in ballot_lines.values())
        over = sum(lines.get('OVER VOTES', 0) for lines in ballot_lines.values())
        self.stdout.write(
            f'{len(totals)} ANC contests, {len(rows)} result rows, {total_votes:,} first-choice votes '
            f'({under:,} undervotes, {over:,} overvotes not stored).'
        )
        if missing:
            self.stdout.write(self.style.WARNING(f'No contest in the file for {len(missing)} district(s): {", ".join(missing)}'))
        self.stdout.write(f'Compared with what is loaded now: {new} new row(s), {len(changed)} vote change(s), '
                          f'{len(existing)} row(s) to remove, {len(leader_changes)} leader change(s).')
        for line in leader_changes:
            self.stdout.write(self.style.WARNING(line))
        for line in changed[:50]:
            self.stdout.write(line)
        if len(changed) > 50:
            self.stdout.write(f'  ... and {len(changed) - 50} more')
        if election.uses_ranked_choice and no_majority:
            self.stdout.write(f'No first-choice majority (ranked-choice rounds will decide) in {len(no_majority)}: {", ".join(no_majority)}')
