"""One-off (but safely re-runnable) backfill of PersonAlias rows from name spellings OpenANC
already has on hand:

  - openanc:         every person's display name (Person.save() adds this for new people; this
                     covers people created before PersonAlias existed)
  - import:          spellings from candidate-import rows a moderator linked to an existing person
  - dcboe_results:   the raw candidate names on ElectionResult rows already linked to a person
  - dcboe_ballot /   the names on the 2026 DCBOE ballot and write-in lists in
    dcboe_write_in:  data/dcboe/excel-clean/, matched to that district's 2026 candidates
  - oanc:            OANC spellings from accent/capitalization notes a moderator rejected (i.e.
                     decided not to change the display name for -- still a real spelling)

data/external_id_lookup.csv is deliberately not a source: its links are already reflected in the
database, and it contains a few rows that point at the wrong person.

Run this locally only. Production gets its aliases from sync_production.sh like every other
editorial model, so the rows (and their primary keys) match local exactly.

Nothing is ever renamed. Names that can't be tied to exactly one person are listed for a human
instead of guessed. Dry run by default; pass --apply to write.

Usage:
  python manage.py backfill_person_aliases
  python manage.py backfill_person_aliases --apply
"""
import csv
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from rapidfuzz import fuzz

from directory.management.commands.check_oanc_commissioners import SUGGESTION_SOURCE_NAME
from directory.models import Candidate, ElectionResult, Person, PersonAlias, PersonImportRow, Suggestion
from directory.names import normalize_name

DEFAULT_DCBOE_DIR = Path(settings.BASE_DIR).parent / 'data' / 'dcboe' / 'excel-clean'
DCBOE_ELECTION_YEAR = 2026
# A DCBOE list name is tied to one of its district's candidates only when it's this close and
# clearly closer than any other candidate there.
DCBOE_MIN_SCORE = 75
DCBOE_MIN_MARGIN = 10
SPELLING_NOTE_RE = re.compile(r'spells the commissioner\'s name "(?P<oanc>[^"]+)", OpenANC has "(?P<ours>[^"]+)"')


class Command(BaseCommand):
    help = 'Backfill PersonAlias rows from existing name spellings (dry run unless --apply).'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Write the aliases (default: dry run).')
        parser.add_argument('--dcboe-dir', default=str(DEFAULT_DCBOE_DIR))

    def handle(self, *args, **options):
        self.proposed = {}   # (person_id, name) -> (source, note)
        self.unresolved = []
        self.existing = set(PersonAlias.objects.values_list('person_id', 'name'))

        # When two sources share a spelling, the first one listed here is the alias's source.
        self.from_display_names()
        self.from_dcboe_lists(Path(options['dcboe_dir']))
        self.from_election_results()
        self.from_rejected_oanc_spellings()
        self.from_import_rows()

        by_source = {}
        for source, _ in self.proposed.values():
            by_source[source] = by_source.get(source, 0) + 1
        verb = 'Added' if options['apply'] else 'Would add'
        summary = ', '.join(f'{n} {source}' for source, n in sorted(by_source.items())) or 'nothing new'
        self.stdout.write(f'{verb} {len(self.proposed)} alias(es): {summary}.')

        if self.unresolved:
            self.stdout.write(self.style.WARNING(f'\n{len(self.unresolved)} name(s) not tied to exactly one person -- review by hand:'))
            for line in self.unresolved:
                self.stdout.write(f'  {line}')

        if options['apply']:
            with transaction.atomic():
                for (person_id, name), (source, note) in self.proposed.items():
                    PersonAlias.objects.get_or_create(
                        person_id=person_id, name=name, defaults={'source': source, 'note': note},
                    )
        else:
            self.stdout.write('\nDry run -- pass --apply to write.')

    def propose(self, person_id, name, source, note=''):
        name = (name or '').strip()  # otherwise verbatim: an alias is the name as the source wrote it
        if not name or not normalize_name(name):
            return
        key = (person_id, name)
        if key in self.existing or key in self.proposed:
            return
        self.proposed[key] = (source, note)

    def from_display_names(self):
        for person_id, full_name in Person.objects.values_list('pk', 'full_name'):
            self.propose(person_id, full_name, PersonAlias.SOURCE_OPENANC)

    def from_import_rows(self):
        rows = PersonImportRow.objects.filter(applied=True, chosen_person__isnull=False).select_related('batch')
        for row in rows:
            self.propose(row.chosen_person_id, row.raw_name, PersonAlias.SOURCE_IMPORT,
                         note=f'Import batch #{row.batch_id}: {row.batch.source_label}'.strip())

    def from_election_results(self):
        results = ElectionResult.objects.filter(candidate__isnull=False).select_related('candidate', 'election', 'district')
        for result in results:
            self.propose(result.candidate.person_id, result.candidate_name_raw, PersonAlias.SOURCE_DCBOE_RESULTS,
                         note=f'{result.election.year} results, SMD {result.district.designator}')

    def from_dcboe_lists(self, dcboe_dir):
        candidates_by_designator = {}
        for candidate in (
            Candidate.objects.filter(election__year=DCBOE_ELECTION_YEAR)
            .select_related('district', 'person').prefetch_related('person__aliases')
        ):
            candidates_by_designator.setdefault(candidate.district.designator, []).append(candidate)

        sources = [
            ('dcboe-ballot-*.csv', PersonAlias.SOURCE_DCBOE_BALLOT),
            ('dcboe-write-in-*.csv', PersonAlias.SOURCE_DCBOE_WRITE_IN),
        ]
        for pattern, source in sources:
            seen = set()
            for path in sorted(dcboe_dir.glob(pattern)):
                if str(DCBOE_ELECTION_YEAR) not in path.name:
                    continue
                with path.open(encoding='utf-8-sig', newline='') as f:
                    for row in csv.DictReader(f):
                        designator = (row.get('ANC-SMD') or row.get('Office') or '').strip()
                        name = ' '.join((row.get('Name') or '').split())
                        if not designator or not name or (designator, name) in seen:
                            continue
                        seen.add((designator, name))
                        self._match_dcboe_name(designator, name, source, path.name, candidates_by_designator)

    def _match_dcboe_name(self, designator, name, source, filename, candidates_by_designator):
        candidates = candidates_by_designator.get(designator, [])
        key = normalize_name(name)
        scored = []
        for candidate in candidates:
            aliases = list(candidate.person.aliases.all())
            if any(a.normalized_name == key for a in aliases):
                scored.append((100.0, candidate))
            else:
                scored.append((max(fuzz.WRatio(key, a.normalized_name) for a in aliases), candidate))
        scored.sort(key=lambda item: -item[0])

        if scored and scored[0][0] >= DCBOE_MIN_SCORE and (len(scored) == 1 or scored[0][0] - scored[1][0] >= DCBOE_MIN_MARGIN):
            self.propose(scored[0][1].person_id, name, source, note=filename)
            return
        options = '; '.join(f'{c.person.full_name} (#{c.person_id}, {score:.0f})' for score, c in scored) or 'no 2026 candidates there'
        self.unresolved.append(f'{filename}: "{name}" in {designator} -- {options}')

    def from_rejected_oanc_spellings(self):
        notes = Suggestion.objects.filter(
            name=SUGGESTION_SOURCE_NAME, status=Suggestion.STATUS_REJECTED,
            suggestion_type__in=[Suggestion.TYPE_GENERAL, Suggestion.TYPE_NAME_SPELLING],
        ).select_related('district')
        for suggestion in notes:
            match = SPELLING_NOTE_RE.search(suggestion.message)
            if not match:
                continue
            oanc_name, our_name = match['oanc'], match['ours']
            people = set(
                PersonAlias.objects.filter(
                    normalized_name=normalize_name(our_name), person__commissioner_terms__district=suggestion.district,
                )
                .values_list('person_id', flat=True)
            )
            if len(people) == 1:
                self.propose(people.pop(), oanc_name, PersonAlias.SOURCE_OANC, note=f'Rejected suggestion #{suggestion.pk}')
            else:
                self.unresolved.append(f'Suggestion #{suggestion.pk}: OANC "{oanc_name}" / ours "{our_name}" in {suggestion.district}')
