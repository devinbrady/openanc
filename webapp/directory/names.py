"""Name normalization shared by the models and the matching code. Kept free of model imports so
models.py can use it without a circular import.

None of this ever changes a name that's stored or displayed: Person.full_name and
PersonAlias.name keep exactly what was entered or scraped, accents included. These functions only
build comparison keys.
"""
import re
import unicodedata

# Disambiguation tags editors add to otherwise-identical display names, e.g.
# "Patricia Williams (Ward 5)". They aren't part of the name any source prints.
_QUALIFIER_RE = re.compile(r'\(\s*ward\s+\d+\s*\)', re.IGNORECASE)
_NON_WORD_RE = re.compile(r'[^\w\s]')


def strip_diacritics(text):
    """'Mónica' -> 'Monica' -- used to compare/search names irrespective of accenting, never to
    change what's actually stored or displayed (that stays exactly as scraped/entered)."""
    normalized = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in normalized if not unicodedata.combining(c))


def normalize_name(name):
    """The lookup key for a name: accents stripped, casefolded, "(Ward N)" tags removed, and
    punctuation (periods, quotes, hyphens, apostrophes, commas) turned into spaces, then
    whitespace collapsed. 'Erika Núñez' and 'ERIKA NUNEZ' share a key; so do
    'Crystal Green-Campbell' and 'Crystal Green Campbell'. Nicknames, initials and suffixes are
    left alone -- those are real differences an alias records explicitly."""
    text = strip_diacritics(name or '').casefold()
    text = _QUALIFIER_RE.sub(' ', text)
    text = _NON_WORD_RE.sub(' ', text).replace('_', ' ')
    return ' '.join(text.split())
