"""Link-preview tags (Open Graph, read by Bluesky and most other sites) on every page."""
import html
import re

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import override_settings
from django.urls import reverse

from directory.tests.base import PageRenderingTestCase
from directory.tests.factories import (
    make_anc,
    make_candidate,
    make_candidate_status,
    make_commissioner_term,
    make_district,
    make_election,
    make_person,
    make_ward,
)
from directory.tests.test_favicon import png_size

SHARE_IMAGE = 'directory/img/share.png'


def meta(page_html, key):
    """Content of the <meta property=key> or <meta name=key> tag, or None if absent."""
    match = re.search(rf'<meta (?:property|name)="{re.escape(key)}" content="([^"]*)">', page_html)
    return html.unescape(match.group(1)) if match else None


class SiteWideTagTests(PageRenderingTestCase):
    @override_settings(CANONICAL_HOST='openanc.org')
    def test_tags_use_canonical_https_urls(self):
        page = self.client.get(reverse('directory:about')).content.decode()
        self.assertEqual(meta(page, 'og:url'), 'https://openanc.org/about/')
        self.assertEqual(meta(page, 'og:image'), f'https://openanc.org/static/{SHARE_IMAGE}')
        self.assertEqual(meta(page, 'og:site_name'), 'OpenANC')
        self.assertEqual(meta(page, 'og:type'), 'website')
        self.assertEqual(meta(page, 'twitter:card'), 'summary_large_image')
        self.assertEqual(meta(page, 'og:image:width'), '1200')
        self.assertEqual(meta(page, 'og:image:height'), '630')
        self.assertTrue(meta(page, 'og:image:alt'))

    def test_urls_fall_back_to_request_host_without_canonical_host(self):
        page = self.client.get(reverse('directory:about')).content.decode()
        self.assertEqual(meta(page, 'og:url'), 'http://testserver/about/')

    def test_og_url_drops_query_string(self):
        page = self.client.get(reverse('directory:about') + '?utm_source=x').content.decode()
        self.assertEqual(meta(page, 'og:url'), 'http://testserver/about/')

    def test_default_title_and_description(self):
        page = self.client.get(reverse('directory:about')).content.decode()
        self.assertEqual(meta(page, 'og:title'), 'About OpenANC')
        description = meta(page, 'og:description')
        self.assertIn('Advisory Neighborhood Commission', description)
        self.assertEqual(meta(page, 'description'), description)

    def test_share_image_is_1200_by_630(self):
        path = finders.find(SHARE_IMAGE)
        self.assertIsNotNone(path)
        self.assertEqual(png_size(path), (1200, 630))


class DetailPageTagTests(PageRenderingTestCase):
    def setUp(self):
        self.ward = make_ward()
        self.anc = make_anc()
        self.district = make_district(anc=self.anc, ward=self.ward)
        self.election = make_election(year=settings.CURRENT_ELECTION_YEAR)

    def get(self, obj):
        return self.client.get(obj.get_absolute_url()).content.decode()

    def test_district_with_commissioner_and_candidates(self):
        commissioner = make_person('Jane Doe')
        make_commissioner_term(commissioner, self.district)
        on_ballot = make_candidate_status('On the Ballot')
        make_candidate(make_person('Ann Lee'), self.election, self.district, status=on_ballot)
        make_candidate(commissioner, self.election, self.district, status=on_ballot)
        withdrawn = make_candidate_status('Withdrew', count_as_candidate=False)
        make_candidate(make_person('Zed Quit'), self.election, self.district, status=withdrawn)

        page = self.get(self.district)
        self.assertEqual(meta(page, 'og:title'), 'SMD 1A01')
        self.assertEqual(
            meta(page, 'og:description'),
            f'Single Member District 1A01 in ANC 1A, Ward 1. Commissioner: Jane Doe. '
            f'{settings.CURRENT_ELECTION_YEAR} candidates: Ann Lee and Jane Doe.',
        )

    def test_district_without_commissioner_or_candidates(self):
        page = self.get(self.district)
        self.assertEqual(
            meta(page, 'og:description'),
            'Single Member District 1A01 in ANC 1A, Ward 1. No current commissioner.',
        )

    def test_district_with_many_candidates_gives_a_count(self):
        status = make_candidate_status()
        for name in ['A One', 'B Two', 'C Three', 'D Four']:
            make_candidate(make_person(name), self.election, self.district, status=status)
        page = self.get(self.district)
        self.assertTrue(meta(page, 'og:description').endswith(
            f'4 candidates in {settings.CURRENT_ELECTION_YEAR}.'
        ))

    def test_person_who_is_commissioner_and_candidate(self):
        person = make_person('Jane Doe')
        make_commissioner_term(person, self.district)
        make_candidate(person, self.election, self.district)
        page = self.get(person)
        self.assertEqual(meta(page, 'og:title'), 'Jane Doe')
        self.assertEqual(
            meta(page, 'og:description'),
            f'Jane Doe is the commissioner for SMD 1A01. '
            f'{settings.CURRENT_ELECTION_YEAR} candidate in SMD 1A01.',
        )

    def test_former_commissioner(self):
        from datetime import date
        person = make_person('Old Timer')
        make_commissioner_term(person, self.district, start_date=date(2019, 1, 2), end_date=date(2021, 1, 2))
        page = self.get(person)
        self.assertEqual(meta(page, 'og:description'), 'Old Timer is a former commissioner for SMD 1A01.')

    def test_person_who_is_only_a_candidate(self):
        person = make_person('New Comer')
        make_candidate(person, self.election, self.district)
        page = self.get(person)
        self.assertEqual(
            meta(page, 'og:description'),
            f'New Comer: {settings.CURRENT_ELECTION_YEAR} candidate in SMD 1A01.',
        )

    def test_anc(self):
        make_district(designator='1A02', anc=self.anc, ward=self.ward)
        page = self.get(self.anc)
        self.assertEqual(meta(page, 'og:title'), 'ANC 1A')
        self.assertEqual(
            meta(page, 'og:description'),
            'ANC 1A: 2 single member districts, with their commissioners and candidates.',
        )

    def test_ward(self):
        make_district(designator='1B01', anc=make_anc('1B'), ward=self.ward)
        page = self.get(self.ward)
        self.assertEqual(meta(page, 'og:title'), 'Ward 1')
        self.assertEqual(
            meta(page, 'og:description'),
            'Ward 1: 2 single member districts in 2 ANCs, with their commissioners and candidates.',
        )
