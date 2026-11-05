from django.test import TestCase

from directory.matching import (
    AMBIGUOUS,
    EXACT,
    NONE,
    UNCONFIRMED,
    build_alias_choices,
    fuzzy_candidates,
    match_for_import,
    match_person_rows,
    resolve_person,
    strip_diacritics,
)
from directory.models import DistrictOverlap, PersonAlias, PersonImportBatch, PersonImportRow
from directory.names import normalize_name
from directory.tests.factories import (
    make_anc,
    make_candidate,
    make_commissioner_term,
    make_district,
    make_election,
    make_person,
    make_ward,
)


class StripDiacriticsTests(TestCase):
    def test_removes_accents(self):
        self.assertEqual(strip_diacritics('Mónica Martínez López'), 'Monica Martinez Lopez')

    def test_leaves_plain_text_unchanged(self):
        self.assertEqual(strip_diacritics('Jaspal Bhatia'), 'Jaspal Bhatia')


class NormalizeNameTests(TestCase):
    def test_accents_and_case(self):
        self.assertEqual(normalize_name('Erika Núñez'), normalize_name('ERIKA NUNEZ'))

    def test_punctuation_and_whitespace(self):
        self.assertEqual(normalize_name('Crystal  Green-Campbell'), 'crystal green campbell')
        self.assertEqual(normalize_name('Harry Thomas, Jr.'), 'harry thomas jr')
        self.assertEqual(normalize_name('Myeasha "My Ty" Smith'), 'myeasha my ty smith')

    def test_ward_qualifier_is_dropped(self):
        self.assertEqual(normalize_name('Patricia Williams (Ward 5)'), 'patricia williams')

    def test_other_parentheticals_are_kept(self):
        self.assertEqual(normalize_name('Jose (Joe) Barrios'), 'jose joe barrios')


class PersonAliasModelTests(TestCase):
    def test_display_name_becomes_an_alias(self):
        person = make_person(full_name='Mónica Martínez López')
        alias = person.aliases.get()
        self.assertEqual(alias.name, 'Mónica Martínez López')
        self.assertEqual(alias.normalized_name, 'monica martinez lopez')
        self.assertEqual(alias.source, PersonAlias.SOURCE_OPENANC)

    def test_renaming_keeps_the_old_name_as_an_alias(self):
        person = make_person(full_name='Erika Nunez')
        person.full_name = 'Erika Núñez'
        person.save()
        self.assertEqual(set(person.aliases.values_list('name', flat=True)), {'Erika Nunez', 'Erika Núñez'})

    def test_set_display_name_keeps_accents_and_slug(self):
        person = make_person(full_name='Erika Nunez')
        slug = person.slug
        accented = person.aliases.create(name='Erika Núñez', source=PersonAlias.SOURCE_OANC)

        person.set_display_name(accented)

        person.refresh_from_db()
        self.assertEqual(person.full_name, 'Erika Núñez')
        self.assertEqual(person.slug, slug)
        self.assertTrue(person.aliases.filter(name='Erika Nunez').exists())

    def test_set_display_name_rejects_someone_elses_alias(self):
        person = make_person(full_name='A Person')
        other_alias = make_person(full_name='B Person').aliases.get()
        with self.assertRaises(ValueError):
            person.set_display_name(other_alias)


class ResolvePersonTests(TestCase):
    def setUp(self):
        self.ward5 = make_ward(number=5)
        self.ward7 = make_ward(number=7)
        self.d5 = make_district(designator='5F03', anc=make_anc(designator='5F'), ward=self.ward5)
        self.d7 = make_district(designator='7C01', anc=make_anc(designator='7C'), ward=self.ward7)
        self.election = make_election(year=2026)
        # The two real Patricia Williamses, told apart in display by their ward tag.
        self.pw5 = make_person(full_name='Patricia Williams (Ward 5)')
        self.pw7 = make_person(full_name='Patricia N. Williams (Ward 7)')
        self.pw7.aliases.create(name='Patricia Williams', source=PersonAlias.SOURCE_DCBOE_BALLOT)
        make_commissioner_term(self.pw5, self.d5)
        make_commissioner_term(self.pw7, self.d7)

    def test_same_name_resolved_by_district(self):
        self.assertEqual(resolve_person('Patricia Williams', district=self.d5).person, self.pw5)
        self.assertEqual(resolve_person('Patricia Williams', district=self.d7).person, self.pw7)

    def test_same_name_without_district_is_unconfirmed(self):
        result = resolve_person('Patricia Williams')
        self.assertEqual(result.status, UNCONFIRMED)
        self.assertEqual(set(result.people), {self.pw5, self.pw7})

    def test_same_ward_counts_as_context(self):
        other_ward5 = make_district(designator='5F04', anc=self.d5.anc, ward=self.ward5)
        self.assertEqual(resolve_person('Patricia Williams', district=other_ward5).person, self.pw5)

    def test_overlapping_district_from_other_cycle_counts_as_context(self):
        old_ward = make_ward(number=3, year=2012)
        old = make_district(designator='3G01', year=2012, anc=make_anc(designator='3G', year=2012), ward=old_ward)
        new = make_district(designator='3G01', anc=make_anc(designator='3G'), ward=make_ward(number=3))
        person = make_person(full_name='Old Timer')
        make_commissioner_term(person, old)
        DistrictOverlap.objects.create(from_district=new, to_district=old, overlap_percentage=0.8)
        self.assertEqual(resolve_person('Old Timer', district=new).status, EXACT)

    def test_unconnected_namesake_is_unconfirmed(self):
        andrew = make_person(full_name='Andrew Davis')
        make_commissioner_term(andrew, make_district(designator='3D04', anc=make_anc(designator='3D'), ward=make_ward(number=3)))
        result = resolve_person('Andrew Davis', district=self.d5)
        self.assertEqual(result.status, UNCONFIRMED)
        self.assertEqual(result.people, [andrew])

    def test_two_people_tied_on_context_are_ambiguous(self):
        twin = make_person(full_name='Patricia Williams')
        make_candidate(twin, self.election, self.d5)
        result = resolve_person('Patricia Williams', district=self.d5, election=self.election)
        self.assertEqual(result.status, EXACT)  # the 2026 candidacy outranks a term
        self.assertEqual(result.person, twin)

        result = resolve_person('Patricia Williams', district=self.d5, election=make_election(year=2028))
        self.assertEqual(result.status, AMBIGUOUS)
        self.assertEqual(set(result.people[:2]), {self.pw5, twin})

    def test_accent_insensitive(self):
        person = make_person(full_name='Erika Núñez')
        make_commissioner_term(person, self.d5)
        self.assertEqual(resolve_person('ERIKA NUNEZ', district=self.d5).person, person)

    def test_unknown_name(self):
        self.assertEqual(resolve_person('Nobody Known', district=self.d5).status, NONE)
        self.assertEqual(resolve_person('   ').status, NONE)


class FuzzyCandidatesTests(TestCase):
    def test_one_entry_per_person_using_best_alias(self):
        person = make_person(full_name='Zachary Adams')
        person.aliases.create(name='Zach Adams', source=PersonAlias.SOURCE_DCBOE_BALLOT)
        make_person(full_name='Zelda Adamson')

        candidates = fuzzy_candidates('Zach Adams', build_alias_choices())

        self.assertEqual(candidates[0]['person_id'], person.pk)
        self.assertEqual(candidates[0]['full_name'], 'Zachary Adams')
        self.assertEqual(candidates[0]['score'], 100.0)
        self.assertEqual(len({c['person_id'] for c in candidates}), len(candidates))

    def test_empty(self):
        self.assertEqual(fuzzy_candidates('Anyone', {}), [])


class MatchForImportTests(TestCase):
    def setUp(self):
        self.district = make_district()
        self.election = make_election(year=2026)

    def test_exact_with_context_links(self):
        person = make_person(full_name='Jaspal Bhatia')
        make_commissioner_term(person, self.district)
        candidates, decision, chosen = match_for_import('Jaspal Bhatia', self.district, self.election, build_alias_choices())
        self.assertEqual(decision, PersonImportRow.DECISION_LINK)
        self.assertEqual(chosen, person.pk)

    def test_near_fuzzy_match_never_links_on_its_own(self):
        person = make_person(full_name='Jaspal Bhatia')
        make_commissioner_term(person, self.district)
        candidates, decision, chosen = match_for_import('Jaspal Bhattia', self.district, self.election, build_alias_choices())
        self.assertEqual(decision, PersonImportRow.DECISION_PENDING)
        self.assertIsNone(chosen)
        self.assertEqual(candidates[0]['person_id'], person.pk)

    def test_unrelated_name_is_new(self):
        make_person(full_name='Jaspal Bhatia')
        _, decision, _ = match_for_import('Zzyzx Qplotnik', self.district, self.election, build_alias_choices())
        self.assertEqual(decision, PersonImportRow.DECISION_NEW)

    def test_no_people_is_new(self):
        candidates, decision, _ = match_for_import('Anyone', self.district, self.election, {})
        self.assertEqual(candidates, [])
        self.assertEqual(decision, PersonImportRow.DECISION_NEW)


class MatchPersonRowsTests(TestCase):
    def test_populates_each_row(self):
        district = make_district()
        person = make_person(full_name='Jaspal Bhatia')
        make_commissioner_term(person, district)
        batch = PersonImportBatch.objects.create(source_label='test', election=make_election(year=2026))
        row = PersonImportRow.objects.create(batch=batch, raw_name='Jaspal Bhatia', district=district)

        match_person_rows(batch)

        row.refresh_from_db()
        self.assertEqual(row.decision, PersonImportRow.DECISION_LINK)
        self.assertEqual(row.chosen_person, person)
        self.assertTrue(row.match_candidates_json)
