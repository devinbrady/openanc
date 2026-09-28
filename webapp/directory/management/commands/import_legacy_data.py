"""
One-time (re-runnable) import of the legacy Google-Sheets-via-CSV data into the Django DB.

Reads straight from the sibling openanc repo's data/ and data/dcboe/ directories -- see
LEGACY_DATA_DIR / LEGACY_DCBOE_DIR below. Safe to re-run: every entity is loaded with
get_or_create/update_or_create keyed on its legacy natural key.
"""
import csv
from datetime import date, datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from directory.models import (
    ANC,
    ANCOverlap,
    Candidate,
    CandidateStatus,
    CommissionerTerm,
    District,
    DistrictOverlap,
    Election,
    ElectionResult,
    MapColor,
    Person,
    Ward,
    WriteInWinner,
)

LEGACY_DATA_DIR = __import__('pathlib').Path(__file__).resolve().parents[4] / 'data'
LEGACY_DCBOE_DIR = LEGACY_DATA_DIR / 'dcboe'

# candidate_status values that drifted from the canonical candidate_statuses.csv enum --
# without this fix, the inner-join style filtering these fed into would have silently
# excluded ~424 historical candidate rows.
CANDIDATE_STATUS_ALIASES = {
    'On Ballot': 'On the Ballot',
    'Write-In': 'Write-In Candidate',
}

APPROXIMATE_START_DATE = date(2019, 1, 2)


def read_csv(path):
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def parse_date(value):
    value = (value or '').strip()
    # A handful of legacy rows use "unknown pickup date" as a sentinel instead of leaving the
    # cell blank.
    if not value or not value[:1].isdigit():
        return None
    return datetime.strptime(value, '%Y-%m-%d').date()


def parse_bool(value):
    return str(value).strip().upper() in ('TRUE', '1', 'YES', 'Y')


def parse_float_list(value):
    if not value:
        return []
    return [float(v.strip()) for v in value.split(',') if v.strip()]


def parse_str_list(value):
    if not value:
        return []
    return [v.strip() for v in value.split(',') if v.strip()]


class Command(BaseCommand):
    help = 'Import legacy CSV data (Google Sheets export) into the Django database.'

    def handle(self, *args, **options):
        with transaction.atomic():
            self.map_colors = self.import_map_colors()
            self.wards = self.import_wards()
            self.ancs = self.import_ancs()
            self.import_anc_overlaps()
            self.districts = self.import_districts()
            self.import_district_neighbors()
            self.import_district_overlaps()
            self.people = self.import_people()
            self.import_commissioner_terms()
            self.elections = self.import_elections()
            self.statuses = self.import_candidate_statuses()
            self.candidates_by_key = self.import_candidates()
            self.external_ids = self.import_external_id_lookup()
            self.import_election_results()
            self.import_write_in_winners()
        self.stdout.write(self.style.SUCCESS('Legacy data import complete.'))

    # -- reference/lookup tables -----------------------------------------------------

    def import_map_colors(self):
        result = {}
        for row in read_csv(LEGACY_DATA_DIR / 'map_colors.csv'):
            obj, _ = MapColor.objects.update_or_create(
                id=int(row['map_color_id']), defaults={'hex_code': row['color_hex']}
            )
            result[row['map_color_id']] = obj
        self.stdout.write(f'  map colors: {len(result)}')
        return result

    def import_wards(self):
        result = {}
        for row in read_csv(LEGACY_DATA_DIR / 'wards.csv'):
            ward_number = int(row['ward_name'].replace('Ward ', ''))
            obj, _ = Ward.objects.update_or_create(
                ward_number=ward_number,
                redistricting_year=int(row['redistricting_year']),
                defaults={'councilmember': row['councilmember']},
            )
            result[row['ward_id']] = obj
        self.stdout.write(f'  wards: {len(result)}')
        return result

    def import_ancs(self):
        result = {}
        rows = read_csv(LEGACY_DATA_DIR / 'ancs.csv')
        for row in rows:
            designator = row['anc_name'].replace('ANC ', '')
            obj, _ = ANC.objects.update_or_create(
                designator=designator,
                redistricting_year=int(row['redistricting_year']),
                defaults=dict(
                    dc_oanc_link=row['dc_oanc_link'],
                    anc_homepage_link=row['anc_homepage_link'],
                    twitter_link=row['twitter_link'],
                    centroid_lon=float(row['centroid_lon']) if row['centroid_lon'] else None,
                    centroid_lat=float(row['centroid_lat']) if row['centroid_lat'] else None,
                    area=int(float(row['area'])) if row['area'] else None,
                    notes=row['notes'],
                ),
            )
            result[row['anc_id']] = obj
        self._anc_overlap_rows = rows
        self.stdout.write(f'  ANCs: {len(result)}')
        return result

    def import_anc_overlaps(self):
        count = 0
        for row in self._anc_overlap_rows:
            from_anc = self.ancs[row['anc_id']]
            to_ids = parse_str_list(row['overlap_ancs'])
            pcts = parse_float_list(row['overlap_percentage'])
            for to_id, pct in zip(to_ids, pcts):
                to_anc = self.ancs.get(to_id)
                if not to_anc:
                    continue
                ANCOverlap.objects.update_or_create(
                    from_anc=from_anc, to_anc=to_anc, defaults={'overlap_percentage': pct}
                )
                count += 1
        self.stdout.write(f'  ANC overlaps: {count}')

    def import_districts(self):
        result = {}
        rows = read_csv(LEGACY_DATA_DIR / 'districts.csv')
        for row in rows:
            obj, _ = District.objects.update_or_create(
                designator=row['smd_name'],
                redistricting_year=int(row['redistricting_year']),
                defaults=dict(
                    anc=self.ancs[row['anc_id']],
                    ward=self.wards[row['ward_id']],
                    map_color=self.map_colors.get(row['map_color_id']),
                    sort_order=int(row['sort_order']),
                    centroid_lon=float(row['centroid_lon']) if row['centroid_lon'] else None,
                    centroid_lat=float(row['centroid_lat']) if row['centroid_lat'] else None,
                    area=int(float(row['area'])) if row['area'] else None,
                    notes=row['notes'],
                    description=row['description'],
                    landmarks=row['landmarks'],
                ),
            )
            result[row['smd_id']] = obj
        self._district_rows = rows
        self.stdout.write(f'  districts: {len(result)}')
        return result

    def import_district_neighbors(self):
        count = 0
        for row in self._district_rows:
            district = self.districts[row['smd_id']]
            for neighbor_id in parse_str_list(row['neighbor_smds']):
                neighbor = self.districts.get(neighbor_id)
                if neighbor:
                    district.neighbors.add(neighbor)
                    count += 1
        self.stdout.write(f'  district neighbor links: {count}')

    def import_district_overlaps(self):
        count = 0
        for row in self._district_rows:
            from_district = self.districts[row['smd_id']]
            to_ids = parse_str_list(row['overlap_smds'])
            pcts = parse_float_list(row['overlap_percentage'])
            for to_id, pct in zip(to_ids, pcts):
                to_district = self.districts.get(to_id)
                if not to_district:
                    continue
                DistrictOverlap.objects.update_or_create(
                    from_district=from_district, to_district=to_district, defaults={'overlap_percentage': pct}
                )
                count += 1
        self.stdout.write(f'  district overlaps: {count}')

    # -- people / commissioners --------------------------------------------------------

    def import_people(self):
        result = {}
        for row in read_csv(LEGACY_DATA_DIR / 'people.csv'):
            obj, _ = Person.objects.update_or_create(
                id=int(row['person_id']),
                defaults=dict(
                    full_name=row['full_name'],
                    twitter_link=row['twitter_link'],
                    mastodon_link=row['mastodon_link'],
                    facebook_link=row['facebook_link'],
                    website_link=row['website_link'],
                ),
            )
            result[row['person_id']] = obj
        self.stdout.write(f'  people: {len(result)}')
        return result

    def import_commissioner_terms(self):
        count = 0
        skipped = 0
        for row in read_csv(LEGACY_DATA_DIR / 'commissioners.csv'):
            district = self.districts.get(row['smd_id'])
            person = self.people.get(row['person_id'])
            if not district or not person:
                skipped += 1
                continue
            start_date = parse_date(row['start_date'])
            CommissionerTerm.objects.update_or_create(
                person=person,
                district=district,
                start_date=start_date,
                defaults=dict(
                    end_date=parse_date(row['end_date']),
                    start_date_is_approximate=(start_date == APPROXIMATE_START_DATE),
                ),
            )
            count += 1
        self.stdout.write(f'  commissioner terms: {count} (skipped {skipped} with unresolved district/person)')

    # -- elections / candidates ----------------------------------------------------------

    def import_elections(self):
        result = {}
        for row in read_csv(LEGACY_DATA_DIR / 'election_dates.csv'):
            obj, _ = Election.objects.update_or_create(
                year=int(row['election_year']),
                defaults=dict(
                    election_date=parse_date(row['election_date']),
                    petition_open_date=parse_date(row['petition_open_date']),
                    petition_close_date=parse_date(row['petition_close_date']),
                ),
            )
            result[row['election_year']] = obj
        self.stdout.write(f'  elections: {len(result)}')
        return result

    def import_candidate_statuses(self):
        result = {}
        for row in read_csv(LEGACY_DATA_DIR / 'candidate_statuses.csv'):
            obj, _ = CandidateStatus.objects.update_or_create(
                name=row['candidate_status'],
                defaults=dict(
                    publish_candidate=parse_bool(row['publish_candidate']),
                    count_as_candidate=parse_bool(row['count_as_candidate']),
                    display_order=int(row['display_order']),
                ),
            )
            result[row['candidate_status']] = obj
        self.stdout.write(f'  candidate statuses: {len(result)}')
        return result

    def import_candidates(self):
        result = {}
        aliased = 0
        skipped = 0
        imported = 0
        for row in read_csv(LEGACY_DATA_DIR / 'candidates.csv'):
            person = self.people.get(row['person_id'])
            district = self.districts.get(row['smd_id'])
            election = self.elections.get(row['election_year'])
            if not person or not district or not election:
                skipped += 1
                continue
            status_name = row['candidate_status']
            if status_name in CANDIDATE_STATUS_ALIASES:
                status_name = CANDIDATE_STATUS_ALIASES[status_name]
                aliased += 1
            status = self.statuses.get(status_name)
            if not status:
                skipped += 1
                continue
            obj, _ = Candidate.objects.update_or_create(
                election=election,
                person=person,
                defaults=dict(
                    district=district,
                    status=status,
                    dcboe_status=row['dcboe_status'],
                    pickup_date=parse_date(row['pickup_date']),
                    filed_date=parse_date(row['filed_date']),
                    write_in_winner_dcboe=parse_bool(row['write-in winner according to DCBOE']),
                    source=row['candidate_source'],
                    source_description=row['candidate_source_description'],
                    source_link=row['candidate_source_link'],
                    dcboe_source_link=row['dcboe_source_link'],
                    dcboe_updated_at=parse_date(row['dcboe_updated_at']),
                    manual_status_source=row['manual_source'],
                    manual_status_source_link=row['manual_source_link'],
                    manual_status_updated_at=parse_date(row['manual_updated_at']),
                    content_updated_at=parse_date(row['updated_at']),
                ),
            )
            result[row['external_id']] = obj
            result[(row['election_year'], row['person_id'])] = obj
            imported += 1
        self.stdout.write(
            f'  candidates: {imported} (normalized {aliased} legacy status values, skipped {skipped} unresolved rows)'
        )
        return result

    def import_external_id_lookup(self):
        result = {}
        for row in read_csv(LEGACY_DATA_DIR / 'external_id_lookup.csv'):
            result[row['external_id']] = row['person_id']
        self.stdout.write(f'  external id lookups: {len(result)}')
        return result

    # -- election results -----------------------------------------------------------------

    def import_election_results(self):
        path = LEGACY_DCBOE_DIR / 'candidate_votes.csv'
        if not path.exists():
            self.stdout.write(self.style.WARNING(f'  no election results found at {path}, skipping'))
            return
        count = 0
        for row in read_csv(path):
            election = self.elections.get(row['election_year'])
            district = self.districts.get(row['smd_id'])
            if not election or not district:
                continue
            person_id = self.external_ids.get(row['external_id']) if row['external_id'] else None
            candidate = self.candidates_by_key.get((row['election_year'], person_id)) if person_id else None
            ElectionResult.objects.update_or_create(
                election=election,
                district=district,
                candidate=candidate,
                candidate_name_raw=row['candidate_name'],
                defaults=dict(
                    votes=int(row['votes']),
                    ranking=int(float(row['ranking'])) if row['ranking'] else None,
                    is_winner=parse_bool(row['winner']),
                    is_write_in_winner=parse_bool(row['write_in_winner']),
                    margin_of_victory=round(float(row['margin_of_victory'])) if row['margin_of_victory'] else None,
                ),
            )
            count += 1
        self.stdout.write(f'  election results: {count}')

    def import_write_in_winners(self):
        path = LEGACY_DCBOE_DIR / 'write_in_winners.csv'
        if not path.exists():
            self.stdout.write(self.style.WARNING(f'  no write-in winners found at {path}, skipping'))
            return
        count = 0
        for row in read_csv(path):
            election = self.elections.get(row['election_year'])
            district = self.districts.get(row['smd_id'])
            if not election or not district:
                continue
            person_id = self.external_ids.get(row['external_id']) if row['external_id'] else None
            person = self.people.get(person_id) if person_id else None
            WriteInWinner.objects.update_or_create(
                election=election,
                district=district,
                candidate_name_raw=row['candidate_name'],
                defaults={'person': person},
            )
            count += 1
        self.stdout.write(f'  write-in winners: {count}')
