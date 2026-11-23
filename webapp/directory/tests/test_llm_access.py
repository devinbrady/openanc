"""The machine-readable side of the site (issue 101): a JSON lookup that answers "who is my ANC
commissioner?" from a latitude/longitude, a JSON view of one district, /llms.txt describing them,
and robots.txt. All of it is cacheable so assistants and crawlers don't need to re-fetch."""
from datetime import timedelta

from django.test import SimpleTestCase
from django.urls import reverse
from django.utils import timezone

from directory.boundaries import designator_at, point_in_geometry
from directory.models import ElectionResult
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

# Points inside real 2022 single-member districts (from directory/geo_data).
POINT_IN_1A01 = (38.9258, -77.0347)
POINT_IN_6_8F01 = (38.8705, -76.9947)
POINT_IN_BALTIMORE = (39.2904, -76.6122)


class PointInGeometryTests(SimpleTestCase):
    SQUARE = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
    HOLE = [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]]

    def test_polygon(self):
        geometry = {'type': 'Polygon', 'coordinates': [self.SQUARE]}
        self.assertTrue(point_in_geometry(geometry, 1, 1))
        self.assertFalse(point_in_geometry(geometry, 11, 1))

    def test_polygon_with_hole(self):
        geometry = {'type': 'Polygon', 'coordinates': [self.SQUARE, self.HOLE]}
        self.assertFalse(point_in_geometry(geometry, 5, 5))
        self.assertTrue(point_in_geometry(geometry, 2, 5))

    def test_multipolygon(self):
        far_square = [[x + 20, y] for x, y in self.SQUARE]
        geometry = {'type': 'MultiPolygon', 'coordinates': [[self.SQUARE], [far_square]]}
        self.assertTrue(point_in_geometry(geometry, 25, 5))
        self.assertFalse(point_in_geometry(geometry, 15, 5))

    def test_designator_at_skips_designators_without_a_boundary(self):
        lat, lng = POINT_IN_1A01
        self.assertEqual(designator_at('district', ['ZZ99', '1A01'], 2022, lng, lat), '1A01')

    def test_none_and_unknown_types(self):
        self.assertFalse(point_in_geometry(None, 1, 1))
        self.assertFalse(point_in_geometry({'type': 'Point', 'coordinates': [1, 1]}, 1, 1))


class LookupApiTests(PageRenderingTestCase):
    def setUp(self):
        self.ward = make_ward()
        self.anc = make_anc(dc_oanc_link='https://anc1a.dc.gov/')
        self.district = make_district(anc=self.anc, ward=self.ward)
        self.commissioner = make_person('Jane Commissioner')
        make_commissioner_term(self.commissioner, self.district)
        self.election = make_election(year=2026)
        self.candidate = make_candidate(make_person('Carl Candidate'), self.election, self.district)

    def _lookup(self, **params):
        return self.client.get(reverse('directory:api_lookup'), params)

    def test_finds_district_and_commissioner_for_a_point(self):
        lat, lng = POINT_IN_1A01
        response = self._lookup(lat=lat, lng=lng)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        data = response.json()
        self.assertEqual(data['district']['designator'], '1A01')
        self.assertEqual(data['district']['url'], 'http://testserver/districts/2022/1A01/')
        self.assertEqual(data['anc']['designator'], '1A')
        self.assertEqual(data['anc']['official_website'], 'https://anc1a.dc.gov/')
        self.assertEqual(data['ward']['number'], 1)
        self.assertEqual(data['commissioner']['name'], 'Jane Commissioner')
        self.assertEqual(data['commissioner']['url'], 'http://testserver' + self.commissioner.get_absolute_url())
        self.assertEqual(data['election']['year'], 2026)
        self.assertEqual([c['name'] for c in data['election']['candidates']], ['Carl Candidate'])

    def test_lon_is_accepted_as_an_alias(self):
        lat, lng = POINT_IN_1A01
        response = self._lookup(lat=lat, lon=lng)
        self.assertEqual(response.json()['district']['designator'], '1A01')

    def test_is_cacheable_and_open_to_other_origins(self):
        lat, lng = POINT_IN_1A01
        response = self._lookup(lat=lat, lng=lng)
        self.assertIn('public', response['Cache-Control'])
        self.assertIn('max-age=3600', response['Cache-Control'])
        self.assertEqual(response['Access-Control-Allow-Origin'], '*')

    def test_vacant_seat_has_null_commissioner(self):
        self.district.commissioner_terms.all().delete()
        lat, lng = POINT_IN_1A01
        data = self._lookup(lat=lat, lng=lng).json()
        self.assertIsNone(data['commissioner'])

    def test_includes_incoming_commissioner(self):
        today = timezone.localdate()
        self.district.commissioner_terms.update(end_date=today + timedelta(days=30))
        incoming = make_person('Ines Incoming')
        make_commissioner_term(
            incoming, self.district, start_date=today + timedelta(days=31), end_date=today + timedelta(days=800)
        )
        lat, lng = POINT_IN_1A01
        data = self._lookup(lat=lat, lng=lng).json()
        self.assertEqual(data['next_commissioner']['name'], 'Ines Incoming')

    def test_includes_election_results(self):
        self.election.results_status = 'unofficial'
        self.election.save()
        ElectionResult.objects.create(
            election=self.election, district=self.district, candidate=self.candidate, votes=321, ranking=1
        )
        ElectionResult.objects.create(election=self.election, district=self.district, votes=7, ranking=2)
        lat, lng = POINT_IN_1A01
        data = self._lookup(lat=lat, lng=lng).json()
        self.assertEqual(data['election']['results_status'], 'unofficial')
        self.assertEqual(
            data['election']['results'],
            [
                {'name': 'Carl Candidate', 'votes': 321, 'is_winner': False, 'is_leading': True},
                {'name': 'Write-ins combined', 'votes': 7, 'is_winner': False, 'is_leading': False},
            ],
        )
        self.assertIsNone(data['election']['ranked_choice'])

    def test_unpublished_candidate_statuses_are_left_out(self):
        hidden = make_candidate_status('Hidden', publish_candidate=False)
        make_candidate(make_person('Hidden Hal'), self.election, self.district, status=hidden)
        lat, lng = POINT_IN_1A01
        names = [c['name'] for c in self._lookup(lat=lat, lng=lng).json()['election']['candidates']]
        self.assertNotIn('Hidden Hal', names)

    def test_district_spanning_two_wards(self):
        ward8 = make_ward(8)
        make_district(designator='6/8F01', anc=make_anc('6/8F'), ward=ward8)
        lat, lng = POINT_IN_6_8F01
        data = self._lookup(lat=lat, lng=lng).json()
        self.assertEqual(data['district']['designator'], '6/8F01')
        self.assertEqual(data['district']['url'], 'http://testserver/districts/2022/6-8F01/')

    def test_point_outside_dc_is_404_with_a_message(self):
        lat, lng = POINT_IN_BALTIMORE
        response = self._lookup(lat=lat, lng=lng)
        self.assertEqual(response.status_code, 404)
        self.assertIn('error', response.json())

    def test_missing_or_bad_coordinates_are_400(self):
        for params in ({}, {'lat': '38.9'}, {'lat': 'abc', 'lng': '-77'}, {'lat': '91', 'lng': '-77'}, {'lat': 'nan', 'lng': '-77'}):
            response = self._lookup(**params)
            self.assertEqual(response.status_code, 400, params)
            self.assertIn('error', response.json())


class DistrictJsonTests(PageRenderingTestCase):
    def setUp(self):
        self.district = make_district()
        make_commissioner_term(make_person('Jane Commissioner'), self.district)

    def test_same_shape_as_lookup(self):
        url = reverse('directory:api_district', kwargs={'year': 2022, 'designator': '1A01'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['district']['designator'], '1A01')
        self.assertEqual(data['commissioner']['name'], 'Jane Commissioner')
        self.assertIn('max-age=3600', response['Cache-Control'])

    def test_unknown_district_is_404_json(self):
        url = reverse('directory:api_district', kwargs={'year': 2022, 'designator': 'ZZ99'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        self.assertIn('error', response.json())


class LlmsTxtAndRobotsTests(PageRenderingTestCase):
    def test_llms_txt_documents_the_lookup(self):
        response = self.client.get('/llms.txt')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/plain'))
        self.assertIn('max-age=86400', response['Cache-Control'])
        body = response.content.decode()
        self.assertTrue(body.startswith('# OpenANC'))
        self.assertIn('http://testserver/api/lookup/?lat=', body)
        self.assertIn('http://testserver/api/districts/2022/1A01/', body)

    def test_robots_txt_allows_crawling_but_not_admin_or_forms(self):
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/plain'))
        body = response.content.decode()
        self.assertIn('User-agent: *', body)
        self.assertIn('Disallow: /admin/', body)
        self.assertIn('Disallow: /suggest/', body)
        self.assertNotIn('Disallow: /\n', body)

    def test_home_page_points_non_js_readers_at_llms_txt(self):
        response = self.client.get(reverse('directory:home'))
        self.assertContains(response, '<noscript>')
        self.assertContains(response, 'href="/llms.txt"')
