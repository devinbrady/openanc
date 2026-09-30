"""Compares the official Office of ANCs commissioner roster against our own current-commissioner
data, and creates a `pending` Suggestion for any district where they disagree:

  - "new_commissioner": we show the seat vacant, OANC shows a real name.
  - "commissioner_change": we show someone currently serving, OANC shows the seat vacant.
  - Both of the above together, when both sides show a different non-vacant name that doesn't
    fuzzy-match closely enough to be confident it's the same person: the current commissioner
    stopping and a new one starting are two separate actions, so they get two suggestions,
    cross-referenced in their messages so a moderator reviews them together.
  - "general", when both sides show what's evidently the same name but disagree only on
    capitalization and/or accented characters (e.g. OANC has "Mónica Martínez López", we have
    "Monica Martinez Lopez") -- not a personnel change, so it's surfaced for a moderator to
    decide whether to update the stored spelling, rather than treated as a resignation+appointment.

OANC's page only ever shows who holds a seat *today* -- it never gives a change date, so
nothing here is auto-applied. Suggestions land in the normal review queue
(/admin/directory/suggestion/) tagged with name="OANC comparison", for a moderator to fill in
the missing date and apply via the existing "Apply selected suggestions" admin action, exactly
like a public submission. Re-running this command won't create duplicates for a district that
already has an OANC-comparison suggestion in flight from a previous run -- pending review, or
approved but not yet applied.

Caching: the OANC site is only ever scraped once per calendar day. The first run each day
fetches every ANC (politely rate-limited) and saves the results to
data/oanc/commissioners_<date>.csv -- same columns/format the old scripts/match_people.py-era
notebook used, so anything else reading that folder keeps working. Every run after that, the
same day, reads that CSV back instead of touching the network at all; this data changes slowly,
and there's no reason to hit a public government site repeatedly. Pass --force-refresh to
re-scrape anyway (e.g. you know something changed and don't want to wait for tomorrow).

Usage:
  python manage.py check_oanc_commissioners
  python manage.py check_oanc_commissioners --dry-run
  python manage.py check_oanc_commissioners --anc 1A
  python manage.py check_oanc_commissioners --force-refresh
"""
import csv
import hashlib
import re
import time
import unicodedata
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from rapidfuzz import fuzz

from directory.matching import strip_diacritics
from directory.models import ANC, District, Suggestion

USER_AGENT = 'Mozilla/5.0 (OpenANC data sync; https://openanc.org)'
REQUEST_DELAY_SECONDS = 2
# Below this fuzzy-match score, two non-vacant names are treated as possibly different people
# and flagged for a human to look at rather than assumed to be a formatting difference.
NAME_MATCH_THRESHOLD = 85
SUGGESTION_SOURCE_NAME = 'OANC comparison'

DEFAULT_CSV_DIR = Path(settings.BASE_DIR).parent / 'data' / 'oanc'
# Matches the columns the old notebook-based pipeline saved to data/oanc/*.csv.
CSV_FIELDNAMES = ['smd_id', 'Name', 'oanc_name', 'is_vacant', 'is_chairperson', 'oanc_hash_id']


def _oanc_hash(designator, oanc_name):
    """Matches scripts/common.py's hash_dataframe(df, ['SMD', 'oanc_name']) -- sha224 of the two
    values comma-joined -- so a CSV this command writes is indistinguishable from one the old
    notebook wrote, for anything that keys off this column."""
    return hashlib.sha224(f'{designator},{oanc_name}'.encode()).hexdigest()


class Command(BaseCommand):
    help = "Compare the official OANC commissioner roster to ours; create review Suggestions for mismatches."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help="Print what would be created, don't save anything.")
        parser.add_argument('--anc', help='Only check this ANC designator (e.g. "1A"), instead of every ANC.')
        parser.add_argument('--csv-dir', default=str(DEFAULT_CSV_DIR), help='Where daily OANC snapshot CSVs live.')
        parser.add_argument(
            '--force-refresh', action='store_true',
            help="Re-scrape the OANC site even if today's CSV snapshot already exists.",
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        csv_dir = Path(options['csv_dir'])
        cache_path = csv_dir / f'commissioners_{timezone.localdate().isoformat()}.csv'

        if cache_path.exists() and not options['force_refresh']:
            self.stdout.write(f'Using cached OANC results from {cache_path} (already checked today).')
            roster_by_designator = self._load_cached_roster(cache_path)
        else:
            roster_by_designator = self._scrape_and_cache(cache_path, dry_run)

        districts = District.objects.filter(redistricting_year=settings.CURRENT_REDISTRICTING_YEAR)
        if options['anc']:
            districts = districts.filter(anc__designator=options['anc'])

        created_counts = {
            Suggestion.TYPE_NEW_COMMISSIONER: 0, Suggestion.TYPE_COMMISSIONER_CHANGE: 0, Suggestion.TYPE_GENERAL: 0,
        }
        skipped_existing = 0
        skipped_no_data = 0

        for district in districts:
            if district.designator not in roster_by_designator:
                skipped_no_data += 1
                continue
            official_name = roster_by_designator[district.designator]

            mismatches = self._classify(district, official_name)
            if not mismatches:
                continue

            # Skip if this district already has an OANC-comparison suggestion that's still in
            # flight -- not just pending review, but also already-approved-and-not-yet-applied:
            # that window (moderator approved it, but hasn't run "Apply selected suggestions"
            # yet) is exactly when a same-day re-run would otherwise see the same live mismatch
            # and create a duplicate that's guaranteed to fail with an overlapping-term error
            # once the first one is applied.
            if Suggestion.objects.filter(
                status__in=[Suggestion.STATUS_PENDING, Suggestion.STATUS_APPROVED],
                applied_at__isnull=True, district=district, name=SUGGESTION_SOURCE_NAME,
            ).exists():
                skipped_existing += 1
                continue

            for suggestion_type, message, structured_data in mismatches:
                created_counts[suggestion_type] += 1
                if dry_run:
                    self.stdout.write(f'[dry-run] {suggestion_type}: {message}')
                    continue
                Suggestion.objects.create(
                    name=SUGGESTION_SOURCE_NAME, district=district, message=message,
                    suggestion_type=suggestion_type, structured_data=structured_data,
                )

        if skipped_no_data:
            self.stderr.write(self.style.WARNING(f'{skipped_no_data} district(s) had no OANC data available -- skipped.'))

        summary = ', '.join(f'{count} {label}' for label, count in created_counts.items() if count)
        self.stdout.write(self.style.SUCCESS(
            f"{'Would create' if dry_run else 'Created'}: {summary or 'nothing -- no mismatches found'}. "
            f'Skipped {skipped_existing} district(s) that already have a pending suggestion from a previous run.'
        ))

    def _scrape_and_cache(self, cache_path, dry_run):
        """Scrapes every ANC's OANC page (politely rate-limited), matches each row to a
        District, and -- unless dry_run -- saves the result to cache_path for the rest of
        today's runs to reuse instead of hitting the network again. Returns {designator:
        oanc_name_or_None} for the whole city."""
        ancs = list(ANC.objects.filter(redistricting_year=settings.CURRENT_REDISTRICTING_YEAR).exclude(dc_oanc_link=''))
        roster = {}
        csv_rows = []

        for i, anc in enumerate(ancs):
            if i > 0:
                time.sleep(REQUEST_DELAY_SECONDS)
            try:
                page_rows = self._fetch_official_roster(anc)
            except requests.RequestException as e:
                self.stderr.write(self.style.WARNING(f'{anc}: could not fetch {anc.dc_oanc_link} ({e}) -- skipped.'))
                continue

            districts_by_suffix = {
                d.designator[-2:]: d
                for d in anc.districts.filter(redistricting_year=settings.CURRENT_REDISTRICTING_YEAR)
            }
            if len(page_rows) != len(districts_by_suffix):
                self.stderr.write(self.style.WARNING(
                    f'{anc}: scraped {len(page_rows)} SMD row(s) but we have {len(districts_by_suffix)} '
                    f'district(s) -- check the page layout.'
                ))

            for row in page_rows:
                district = districts_by_suffix.get(row['smd_text'][-2:])
                if district is None:
                    self.stderr.write(self.style.WARNING(f'{anc}: could not match scraped SMD "{row["smd_text"]}" to one of our districts.'))
                    continue
                roster[district.designator] = row['oanc_name']
                oanc_name_for_csv = row['oanc_name'] or 'Vacant'
                csv_rows.append({
                    'smd_id': f'smd_{district.redistricting_year}_{district.designator}',
                    'Name': row['raw_text'],
                    'oanc_name': oanc_name_for_csv,
                    'is_vacant': row['oanc_name'] is None,
                    'is_chairperson': 'chairperson' in row['raw_text'].lower(),
                    'oanc_hash_id': _oanc_hash(district.designator, oanc_name_for_csv),
                })

        if dry_run:
            self.stdout.write(f'[dry-run] would save {len(csv_rows)} row(s) to {cache_path}.')
        else:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
                writer.writeheader()
                writer.writerows(csv_rows)
            self.stdout.write(self.style.SUCCESS(f'Saved {len(csv_rows)} row(s) to {cache_path}.'))

        return roster

    def _load_cached_roster(self, cache_path):
        """Returns {designator: oanc_name_or_None} from a CSV this command (or the old notebook)
        already saved today -- smd_id is "smd_<year>_<designator>"."""
        roster = {}
        with open(cache_path, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                designator = row['smd_id'].split('_', 2)[-1]
                oanc_name = row['oanc_name']
                roster[designator] = None if oanc_name.strip().lower() == 'vacant' else oanc_name
        return roster

    def _fetch_official_roster(self, anc):
        """Returns a list of {'smd_text', 'raw_text', 'oanc_name'} dicts, one per SMD row on
        this ANC's OANC page. oanc_name is None when OANC lists that seat as vacant; raw_text is
        the whole cell's text (name plus any officer title, exactly as the old notebook's `Name`
        CSV column captured it)."""
        response = requests.get(anc.dc_oanc_link, headers={'User-Agent': USER_AGENT}, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')
        table = soup.find('table')
        if table is None:
            return []

        rows = []
        for row in (table.find('tbody') or table).find_all('tr'):
            cells = row.find_all('td')
            if len(cells) < 2:
                continue
            smd_text = cells[0].get_text(strip=True)
            if smd_text.upper() == 'SMD':
                continue  # a header row rendered as a plain <tr> instead of inside <thead>
            raw_text = self._normalize_text(cells[1].get_text())
            # OANC sometimes wraps "Vacant" itself in an <em> (same markup it uses for an officer
            # title), so it can't be detected on the post-_extract_name text -- stripping every
            # <em> would remove "Vacant" too and leave an empty string. Check the untouched
            # raw_text instead: a title (when there is one) is always appended after the name/
            # status with no separator, so a vacant seat's raw_text always starts with "Vacant"
            # ("Vacant", "VacantSecretary", "VacantTreasurer", ...).
            is_vacant = raw_text.lower().startswith('vacant')
            name = None if is_vacant else self._extract_name(cells[1])
            rows.append({
                'smd_text': smd_text,
                'raw_text': raw_text,
                'oanc_name': name,
            })
        return rows

    def _normalize_text(self, text):
        text = unicodedata.normalize('NFC', text)
        return re.sub(r'\s+', ' ', text).strip()

    def _extract_name(self, name_cell):
        """The officer title (Chairperson, Treasurer, etc.), when present, is always wrapped in
        an <em> -- strip that out first, then take whatever text remains as the name. Mutates
        name_cell in place (removes the <em>), so call this after capturing any text you need
        from the cell as a whole (e.g. _fetch_official_roster's raw_text).

        Not just the cell's first line/text node: some names include an accented character
        wrapped in its own <span> (a font-fallback quirk of the site, not a title), splitting a
        single name across several text nodes -- e.g. "Mónica Martínez López" arrives as "M" +
        "ónica Martínez Ló" (a <span> around the accented letters) + "pez". Concatenating every
        remaining text node with no separator reassembles that correctly, since a real name's
        own internal spaces already live inside one contiguous text node.
        """
        for em in name_cell.find_all('em'):
            em.decompose()
        return self._normalize_text(name_cell.get_text())

    def _classify(self, district, official_name):
        """Returns a list of (suggestion_type, message, structured_data) tuples -- empty if
        there's no discrepancy worth flagging. When both sides show a different non-vacant name,
        that's two separate actions (the old commissioner stopped, a new one started), so two
        suggestions come back, each mentioning the other so a moderator reviews them together --
        unless the difference is only capitalization/accented characters, which is an editorial
        spelling question, not a personnel change (see the module docstring)."""
        current_term = district.current_commissioner_term
        our_name = current_term.person.full_name if current_term else None

        if official_name is None and our_name is None:
            return []

        if official_name is not None and our_name is None:
            message = (
                f'Office of ANCs lists {official_name} as the commissioner for {district}, but '
                f"OpenANC currently shows this seat as vacant. Found by the automated OANC comparison."
            )
            return [(Suggestion.TYPE_NEW_COMMISSIONER, message, {'district_id': district.id, 'person_name': official_name})]

        if official_name is None and our_name is not None:
            message = (
                f'Office of ANCs lists {district} as vacant, but OpenANC currently shows '
                f'{our_name} as the sitting commissioner. Found by the automated OANC comparison.'
            )
            return [(Suggestion.TYPE_COMMISSIONER_CHANGE, message, {'district_id': district.id})]

        if official_name == our_name:
            return []

        if strip_diacritics(official_name).casefold() == strip_diacritics(our_name).casefold():
            # Same person -- the two sides just disagree on capitalization and/or accented
            # characters (e.g. "KSO" vs "Kso", "López" vs "Lopez"). Not a personnel change, so it
            # never gets the resign+appoint treatment below; whether to update OpenANC's spelling
            # to match is an editorial call for a moderator, not something to auto-apply.
            message = (
                f'For {district}, Office of ANCs spells the commissioner\'s name "{official_name}", '
                f'OpenANC has "{our_name}" -- looks like the same person, just a difference in '
                f'capitalization and/or accented characters. Update the stored name if that '
                f'spelling is preferred. Found by the automated OANC comparison.'
            )
            return [(Suggestion.TYPE_GENERAL, message, {})]

        score = fuzz.WRatio(official_name, our_name)
        if score >= NAME_MATCH_THRESHOLD:
            return []

        shared_context = (
            f'(Office of ANCs now lists {official_name} for {district}, OpenANC still shows '
            f'{our_name}; name match score {score:.0f}/100. Found by the automated OANC '
            f'comparison -- review this together with the paired suggestion for this district.)'
        )
        change_message = f'{our_name} appears to no longer be serving {district}. {shared_context}'
        new_message = f'{official_name} appears to now be serving {district}. {shared_context}'
        return [
            (Suggestion.TYPE_COMMISSIONER_CHANGE, change_message, {'district_id': district.id}),
            (Suggestion.TYPE_NEW_COMMISSIONER, new_message, {'district_id': district.id, 'person_name': official_name}),
        ]
