"""Fuzzy-matches names against existing Person rows for the candidate-import review tool
(see admin_views.py). Uses rapidfuzz -- the maintained successor to the old scripts/
match_people.py pipeline's fuzzywuzzy.
"""
from rapidfuzz import fuzz, process

from .models import Person, PersonImportRow

# Auto-preselect "link to an existing person" above this score, "create a new person" below
# this one; the band in between is left for a human to decide in the review UI.
LINK_THRESHOLD = 95
NEW_THRESHOLD = 70


def build_person_choices():
    return {person.id: person.full_name for person in Person.objects.all()}


def match_name(raw_name, choices, limit=5):
    """Returns (candidates, decision). candidates is a list of {person_id, full_name, score}
    (best first, empty if there's nothing to match against). decision is one of
    PersonImportRow.DECISION_LINK / DECISION_NEW / DECISION_PENDING, based on the top score."""
    if not choices:
        return [], PersonImportRow.DECISION_NEW

    results = process.extract(raw_name, choices, scorer=fuzz.WRatio, limit=limit)
    candidates = [
        {'person_id': person_id, 'full_name': full_name, 'score': round(score, 1)}
        for full_name, score, person_id in results
    ]

    top_score = candidates[0]['score'] if candidates else 0
    if top_score >= LINK_THRESHOLD:
        decision = PersonImportRow.DECISION_LINK
    elif top_score < NEW_THRESHOLD:
        decision = PersonImportRow.DECISION_NEW
    else:
        decision = PersonImportRow.DECISION_PENDING
    return candidates, decision


def match_person_rows(batch):
    """Runs matching for every row in an import batch, storing results (and an auto-preselected
    decision) directly on each PersonImportRow."""
    choices = build_person_choices()
    for row in batch.rows.all():
        candidates, decision = match_name(row.raw_name, choices)
        row.match_candidates_json = candidates
        row.best_match_score = candidates[0]['score'] if candidates else None
        row.decision = decision
        row.chosen_person_id = candidates[0]['person_id'] if decision == PersonImportRow.DECISION_LINK else None
        row.save()
