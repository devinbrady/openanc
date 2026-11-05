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


@register.filter
def person_search_key(person):
    """The client-side person filter's search key (see person_list.html): the display name
    accent-stripped and lowercased, followed by every other alias's normalized form, so typing
    "Zach Adams" finds Zachary Adams. Aliases are never shown on the page, only matched."""
    keys = [_strip_diacritics(person.full_name).lower()]
    for alias in person.aliases.all():
        if alias.normalized_name and alias.normalized_name not in keys:
            keys.append(alias.normalized_name)
    return ' | '.join(keys)


@register.filter
def floatformat_percent(fraction):
    """0.4597 -> '46.0%'."""
    return f'{fraction * 100:.1f}%'
