from django.test import TestCase
from django.urls import reverse

from directory.tests.factories import make_anc, make_district, make_ward
from directory.urls import DesignatorConverter


class DesignatorConverterTests(TestCase):
    def setUp(self):
        self.converter = DesignatorConverter()

    def test_to_python_uppercases_and_restores_slash(self):
        self.assertEqual(self.converter.to_python('6-8f01'), '6/8F01')

    def test_to_python_leaves_plain_designators_alone(self):
        self.assertEqual(self.converter.to_python('1a01'), '1A01')

    def test_to_url_replaces_slash_with_dash(self):
        self.assertEqual(self.converter.to_url('6/8F01'), '6-8F01')

    def test_round_trip(self):
        original = '3/4G01'
        self.assertEqual(self.converter.to_python(self.converter.to_url(original)), original)


class DistrictSummaryApiTests(TestCase):
    """Every dual-ward SMD designator should resolve through the API endpoint the map's
    JS hits -- this is the exact class of bug that broke 6/8F01 (smd_id truncation)."""

    def test_all_slash_designators_resolve(self):
        ward = make_ward()
        ancs = {}
        for designator, anc_designator in [
            ('3/4G01', '3/4G'), ('3/4G02', '3/4G'), ('6/8F01', '6/8F'), ('6/8F05', '6/8F'),
        ]:
            if anc_designator not in ancs:
                ancs[anc_designator] = make_anc(designator=anc_designator)
            anc = ancs[anc_designator]
            district = make_district(designator=designator, anc=anc, ward=ward)
            url = reverse(
                'directory:district_summary',
                kwargs={'year': district.redistricting_year, 'designator': designator},
            )
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, f'{designator} -> {url}')
            self.assertContains(response, f'SMD {designator}')
