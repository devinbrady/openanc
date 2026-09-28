import datetime

from django.core.management import call_command
from django.test import TestCase

from directory.models import CommissionerTerm, SiteUpdate
from directory.tests.factories import make_commissioner_term, make_district, make_person


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
