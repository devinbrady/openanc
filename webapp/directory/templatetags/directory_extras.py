from django import template

from directory.matching import strip_diacritics as _strip_diacritics

register = template.Library()


@register.filter
def as_percentage(fraction):
    """Convert a 0-1 fraction (how overlap_percentage is stored) to a 0-100 percentage."""
    return fraction * 100


@register.filter
def strip_diacritics(text):
    """'Mónica' -> 'Monica' -- used to build a plain-ASCII search key for the client-side person
    filter (see person_list.html), so typing "Lopez" finds "López" too."""
    return _strip_diacritics(text)
