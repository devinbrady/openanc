"""Loads DCBOE's ranked-choice (RCV) round-by-round results for ANC contests.

DCBOE publishes RCV results in numbered releases on the RCV tab of its results site; each
tabulated contest links to an RCVis visualization. This reads DCBOE's list for a release (the
newest unless --release names another), reads each ANC contest's tabulation from its RCVis page,
and stores the rounds as RankedChoiceContest + RankedChoiceTally. It also sets
ElectionResult.rcv_outcome (elected / eliminated) on the first-choice rows, so the site shows the
ranked-choice winner as leading -- and, for certified results, as the winner.

Run import_election_results first: every name in a tabulation must match a first-choice result
row in that district (the RCTab files use the same ballot spellings), or nothing is written.

Each run replaces what's stored for the election: contests in the release are rewritten, and
contests that aren't in it any more are removed. Pages and contest lists are cached in
data/rcvis/ (see directory/rcv.py), so re-running costs no requests to RCVis.

  python manage.py import_rcv_results --year 2026           # dry run, newest release
  python manage.py import_rcv_results --year 2026 --apply
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from directory import rcv
from directory.models import Election, ElectionResult, RankedChoiceContest, RankedChoiceTally


class Command(BaseCommand):
    help = "Import DCBOE's ranked-choice round-by-round ANC results (dry run unless --apply)."

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, required=True)
        parser.add_argument('--release', help="DCBOE's release name, e.g. 'Preliminary RCV Results 5 - "
                                              "Published November 20, 2026'. Defaults to the newest.")
        parser.add_argument('--election-code', help="DCBOE's code for the election (default: <year>-General-Election).")
        parser.add_argument('--cache-dir', default=str(rcv.DEFAULT_CACHE_DIR))
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        try:
            election = Election.objects.get(year=options['year'])
        except Election.DoesNotExist:
            raise CommandError(f'No {options["year"]} election.')
        if not election.uses_ranked_choice:
            raise CommandError(f"The {election.year} election doesn't use ranked choice.")

        fetcher = rcv.Fetcher(
            options['election_code'] or f'{election.year}-General-Election',
            cache_dir=options['cache_dir'], log=self.stdout.write,
        )
        try:
            release = self.pick_release(fetcher, options['release'])
            contests = self.load_contests(election, fetcher, release)
        except rcv.RcvError as e:
            raise CommandError(str(e)) from e

        self.report(election, release, contests)
        if not options['apply']:
            self.stdout.write('Dry run: nothing written. Re-run with --apply to save.')
            return
        with transaction.atomic():
            self.save(election, release, contests)
        self.stdout.write(self.style.SUCCESS(f'Saved {len(contests)} ranked-choice contest(s).'))

    def pick_release(self, fetcher, requested):
        releases = fetcher.releases()
        if not releases:
            raise CommandError(f'DCBOE has not published any RCV results for {fetcher.election_code} yet.')
        if requested is None:
            return releases[0]
        if requested not in releases:
            raise CommandError(f'"{requested}" is not one of DCBOE\'s RCV releases: {"; ".join(releases)}')
        return requested

    def load_contests(self, election, fetcher, release):
        """[(district, url, rounds, results_by_name)] for each ANC contest in the release.
        Raises CommandError, before anything is written, if any contest doesn't line up."""
        # The first-choice rows, by district and ballot name: {designator: (district, {name: result})}
        results = {}
        for result in ElectionResult.objects.filter(election=election).select_related('district'):
            district, by_name = results.setdefault(result.district.designator, (result.district, {}))
            by_name[result.candidate_name_raw] = result

        contests, errors = [], []
        for entry in fetcher.contests(release):
            designator = rcv.office_designator(entry['OfficeName'])
            if designator is None:
                continue
            url = entry['VisualizationSourceURL']
            summary = fetcher.summary(url)
            in_file = rcv.summary_designator(summary)
            if in_file != designator:
                errors.append(f'{rcv.rcvis_slug(url)} is contest {in_file}, but DCBOE lists it for {designator}.')
                continue
            rounds = rcv.parse_rounds(summary)
            district, by_name = results.get(designator, (None, {}))
            problems = [
                f'{designator}: "{name}" has no first-choice result row. '
                'Run import_election_results first, or fix the name.'
                for name in sorted({name for rnd in rounds for name in rnd.tallies} - set(by_name))
            ]
            if not rounds or len(rounds[-1].elected) != 1:
                problems.append(f'{designator}: expected one winner in the last round.')
            if problems:
                errors.extend(problems)
                continue
            contests.append((district, url, rounds, by_name))
        if errors:
            raise CommandError('Nothing written:\n  ' + '\n  '.join(errors))
        return contests

    def report(self, election, release, contests):
        self.stdout.write(f'{release}: {len(contests)} ANC contest(s) tabulated.')
        current = {c.district_id: c for c in RankedChoiceContest.objects.filter(election=election)}
        for district, url, rounds, by_name in contests:
            winner = rounds[-1].elected[0]
            leader = next((name for name, r in by_name.items() if r.ranking == 1), None)
            plural = 'round' if len(rounds) == 1 else 'rounds'
            line = f'  {district.designator}: {len(rounds)} {plural}, {winner} elected'
            if leader and leader != winner:
                line += f' (first-choice leader was {leader})'
            old = current.pop(district.pk, None)
            if old and old.rcvis_url != url:
                line += f' [was {old.rcvis_url}]'
            self.stdout.write(self.style.WARNING(line) if leader and leader != winner else line)
        for old in current.values():
            self.stdout.write(self.style.WARNING(f'  {old.district.designator}: no longer tabulated, will be removed.'))

    def save(self, election, release, contests):
        final = election.results_are_final
        tabulated = {district.pk for district, *_ in contests}
        RankedChoiceContest.objects.filter(election=election).exclude(district__in=tabulated).delete()
        ElectionResult.objects.filter(election=election).exclude(district__in=tabulated).update(rcv_outcome='')

        for district, url, rounds, by_name in contests:
            contest, _ = RankedChoiceContest.objects.update_or_create(
                election=election, district=district,
                defaults={'rcvis_url': url, 'release_name': release, 'release_date': rcv.release_date(release),
                          'num_rounds': len(rounds)},
            )
            contest.tallies.all().delete()
            tallies = []
            for rnd in rounds:
                for name, votes in rnd.tallies.items():
                    outcome = (RankedChoiceTally.OUTCOME_ELECTED if name in rnd.elected
                               else RankedChoiceTally.OUTCOME_ELIMINATED if name in rnd.eliminated else '')
                    tallies.append(RankedChoiceTally(
                        contest=contest, round_number=rnd.number, candidate=by_name[name].candidate,
                        candidate_name_raw=name, votes=votes, outcome=outcome,
                    ))
                tallies.append(RankedChoiceTally(
                    contest=contest, round_number=rnd.number, candidate_name_raw='Inactive ballots',
                    is_inactive=True, votes=rnd.inactive,
                ))
            RankedChoiceTally.objects.bulk_create(tallies)

            winner = rounds[-1].elected[0]
            for name, result in by_name.items():
                elected = name == winner
                result.rcv_outcome = ElectionResult.RCV_ELECTED if elected else ElectionResult.RCV_ELIMINATED
                fields = ['rcv_outcome']
                if final:
                    result.is_winner = elected
                    result.is_write_in_winner = elected and result.candidate_id is None
                    fields += ['is_winner', 'is_write_in_winner']
                result.save(update_fields=fields)
