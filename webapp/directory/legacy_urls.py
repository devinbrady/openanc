"""Permanent redirects from the old static site's URLs (openanc.org/map_2022/ancs/1A.html etc.)
to their Django equivalents, so links people made to the old site keep working.

The static site was served by GitHub Pages, which answered both `/about.html` and `/about`,
so every pattern here accepts an optional `.html`.
"""
import csv
import unicodedata
from functools import cache
from pathlib import Path

from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import re_path

from .models import Person

# Old person page name (e.g. 'AaronBrown', from data/people.csv's person_name_id) -> Person pk.
# Person pks were carried over from the old person_id when the data was imported.
LEGACY_PEOPLE_CSV = Path(__file__).resolve().parent / 'legacy_people.csv'

# The old site wrote the two dual-ward ANCs without their slash: 34G, 68F.
DUAL_WARD_PREFIXES = {'34': '3/4', '68': '6/8'}

# A few old pages used a single-ward name for what is now a dual-ward ANC.
RENAMED_ANCS = {(2012, '3G'): '3/4G', (2022, '8F'): '6/8F'}

HTML = r'(?:\.html)?'


def _normalize(value):
    return unicodedata.normalize('NFC', value).casefold()


@cache
def legacy_person_ids():
    with open(LEGACY_PEOPLE_CSV, newline='') as f:
        return {_normalize(row['legacy_name']): int(row['person_id']) for row in csv.DictReader(f)}


def _designator(year, legacy):
    legacy = legacy.upper()
    prefix = DUAL_WARD_PREFIXES.get(legacy[:2])
    if prefix:
        return prefix + legacy[2:]
    renamed = RENAMED_ANCS.get((year, legacy[:2]))
    return renamed + legacy[2:] if renamed else legacy


def to_page(request, name):
    return redirect(name, permanent=True)


def to_anc(request, year, designator):
    year = int(year)
    return redirect('directory:anc_detail', year=year, designator=_designator(year, designator), permanent=True)


def to_district(request, year, designator):
    year = int(year)
    return redirect('directory:district_detail', year=year, designator=_designator(year, designator), permanent=True)


def to_ward(request, year, number):
    return redirect('directory:ward_detail', year=int(year), number=int(number), permanent=True)


def to_person(request, legacy_name, extension=None):
    person_id = legacy_person_ids().get(_normalize(legacy_name))
    if person_id is None:
        if extension:
            raise Http404('No person with that old page name.')
        # Not an old name, so probably a new slug typed without its trailing slash; do what
        # APPEND_SLASH would have done if this pattern hadn't matched.
        return redirect(f'{request.path}/', permanent=True)
    return redirect(get_object_or_404(Person, pk=person_id), permanent=True)


urlpatterns = [
    re_path(rf'^index{HTML}$', to_page, {'name': 'directory:home'}),
    re_path(rf'^(?:list|incumbents){HTML}$', to_page, {'name': 'directory:district_list'}),
    re_path(rf'^about{HTML}$', to_page, {'name': 'directory:about'}),
    re_path(rf'^updates{HTML}$', to_page, {'name': 'directory:updates'}),
    re_path(rf'^counts{HTML}$', to_page, {'name': 'directory:counts'}),
    re_path(rf'^contested{HTML}$', to_page, {'name': 'directory:contested'}),
    re_path(r'^people/index\.html$', to_page, {'name': 'directory:person_list'}),
    re_path(rf'^map_\d{{4}}/(?:ancs|wards)/(?:index{HTML})?$', to_page, {'name': 'directory:district_list'}),
    re_path(rf'^map_(?P<year>\d{{4}})/ancs/(?P<designator>\d{{1,2}}[A-Za-z]){HTML}$', to_anc),
    re_path(rf'^map_(?P<year>\d{{4}})/ancs/districts/(?P<designator>\d{{1,2}}[A-Za-z]\d{{2}}){HTML}$', to_district),
    re_path(rf'^map_(?P<year>\d{{4}})/wards/(?P<number>\d){HTML}$', to_ward),
    # No trailing slash, so this never shadows the new /people/<slug>/ pages.
    re_path(r'^people/(?P<legacy_name>[^/]+?)(?P<extension>\.html)?$', to_person),
]
