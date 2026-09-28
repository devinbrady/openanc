"""Small helpers for building the minimal object graph a test needs.

Not a full factory library on purpose -- the model graph here is shallow enough that plain
functions with sensible defaults are easier to read than introducing factory_boy.
"""
from datetime import timedelta

from django.utils import timezone

from directory.models import (
    ANC,
    Candidate,
    CandidateStatus,
    CommissionerTerm,
    District,
    Election,
    Person,
    Ward,
)


def make_ward(number=1, year=2022):
    return Ward.objects.create(ward_number=number, redistricting_year=year, councilmember='Test Councilmember')


def make_anc(designator='1A', year=2022):
    return ANC.objects.create(designator=designator, redistricting_year=year)


def make_district(designator='1A01', year=2022, anc=None, ward=None, **kwargs):
    anc = anc or make_anc(year=year)
    ward = ward or make_ward(year=year)
    return District.objects.create(designator=designator, redistricting_year=year, anc=anc, ward=ward, **kwargs)


def make_person(full_name='Jane Doe'):
    return Person.objects.create(full_name=full_name)


def make_commissioner_term(person, district, start_date=None, end_date=None, **kwargs):
    today = timezone.localdate()
    start_date = start_date or today - timedelta(days=100)
    end_date = end_date or today + timedelta(days=500)
    return CommissionerTerm.objects.create(
        person=person, district=district, start_date=start_date, end_date=end_date, **kwargs
    )


def make_election(year=2026, **kwargs):
    return Election.objects.create(year=year, **kwargs)


def make_candidate_status(name='On the Ballot', **kwargs):
    return CandidateStatus.objects.create(name=name, **kwargs)


def make_candidate(person, election, district, status=None, **kwargs):
    status = status or make_candidate_status()
    return Candidate.objects.create(person=person, election=election, district=district, status=status, **kwargs)
