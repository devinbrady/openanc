
import pytest

from scripts.urls import link_slug, format_name_for_url



def test_link_slug():
    assert link_slug('smd_1A01') == '1A01'


def test_format_name_for_url():
    assert format_name_for_url('Patrick_O\'Shea') == 'PatrickOShea'