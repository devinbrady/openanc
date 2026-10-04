import datetime

from django.core.management import call_command
from django.test import TestCase

from directory.models import Candidate, CommissionerTerm, SiteUpdate
from directory.tests.factories import (
    make_candidate, make_commissioner_term, make_district, make_election, make_person,
)


class DraftSiteUpdateTests(TestCase):
    def test_creates_unpublished_draft_mentioning_the_district(self):
        district = make_district(designator='1A01')
        outgoing = make_person(full_name='Outgoing Commissioner')
        incoming = make_person(full_name='Incoming Commissioner')
        today = datetime.date.today()

        term = make_commissioner_term(
            outgoing, district, start_date=today - datetime.timedelta(days=400), end_date=today + datetime.timedelta(days=1),
        )
        term.end_date = today
        term.save()
        make_commissioner_term(incoming, district, start_date=today, end_date=today + datetime.timedelta(days=730))

        call_command('draft_site_update')

        draft = SiteUpdate.objects.get()
        self.assertFalse(draft.is_published)
        self.assertEqual(draft.date, today)
        self.assertIn('1A01', draft.body)
        self.assertIn('Incoming Commissioner', draft.body)

    def test_no_changes_creates_no_draft(self):
        call_command('draft_site_update')
        self.assertEqual(SiteUpdate.objects.count(), 0)

    def test_since_defaults_to_last_published_update(self):
        old = datetime.date.today() - datetime.timedelta(days=30)
        SiteUpdate.objects.create(date=old, body='old news', is_published=True)
        make_person(full_name='Someone New')

        call_command('draft_site_update')

        draft = SiteUpdate.objects.get(is_published=False)
        self.assertIn('Someone New', draft.body)


class EditorialRowCountsTests(TestCase):
    def run_command(self):
        from io import StringIO
        out = StringIO()
        call_command('editorial_row_counts', stdout=out)
        return dict(
            (label, rest.split())
            for label, rest in (line.split(': ') for line in out.getvalue().splitlines())
        )

    def test_hash_changes_when_a_row_is_edited_without_changing_the_count(self):
        person = make_person(full_name='Before')
        before = self.run_command()['directory.Person']

        person.full_name = 'After'
        person.save()
        after = self.run_command()['directory.Person']

        self.assertEqual(before[0], after[0])
        self.assertNotEqual(before[1], after[1])

    def test_hash_is_stable_when_nothing_changes(self):
        make_person(full_name='Same')
        self.assertEqual(self.run_command(), self.run_command())

    def test_hash_ignores_sub_millisecond_timestamp_differences(self):
        # Production's copy of a pushed row has timestamps truncated to milliseconds by the
        # JSON fixture; that alone must not make the tables look different.
        candidate = make_candidate(make_person(), make_election(), make_district())
        stamp = datetime.datetime(2026, 1, 1, 12, 0, 0, 123456, tzinfo=datetime.timezone.utc)
        Candidate.objects.filter(pk=candidate.pk).update(created_at=stamp)
        precise = self.run_command()['directory.Candidate']

        Candidate.objects.filter(pk=candidate.pk).update(created_at=stamp.replace(microsecond=123000))
        truncated = self.run_command()['directory.Candidate']
        self.assertEqual(precise, truncated)
