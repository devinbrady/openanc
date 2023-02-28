
import pytest

from scripts.urls import *


def test_generate_link():
    assert generate_link('smd_2A01', 'A great link', link_source='anc') == '<a href="../../map_2012/ancs/districts/2A01.html">A great link</a>'


def test_generate_url():
    assert generate_url('smd_2022_2A01', link_source='district') == '../../../map_2022/ancs/districts/2A01.html'


def test_relative_link_prefix():
    assert relative_link_prefix('anc', 'district', redistricting_year='2022') == '../../map_2022/ancs/districts/'


def test_link_slug():
    assert link_slug('smd_1A01') == '1A01'


def test_format_name_for_url():
    assert format_name_for_url('Patrick_O\'Shea') == 'PatrickOShea'