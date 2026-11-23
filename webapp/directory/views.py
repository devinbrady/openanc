import logging
import math
from collections import defaultdict

from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_safe
from django.views.generic import DetailView, ListView, TemplateView
from django.views.generic.edit import CreateView

from .analytics import count_in_goatcounter
from .boundaries import boundary_geometry, designator_at
from .forms import SuggestionForm
from .models import (
    ANC,
    Candidate,
    CandidateStatus,
    CommissionerTerm,
    District,
    Election,
    ElectionResult,
    Person,
    PersonSlugRedirect,
    RankedChoiceContest,
    RankedChoiceTally,
    SiteUpdate,
    Suggestion,
    Ward,
    WriteInWinner,
    resolve_current_commissioner_term,
)

logger = logging.getLogger(__name__)


def mapbox_context():
    return {
        'mapbox_access_token': settings.MAPBOX_ACCESS_TOKEN,
        'mapbox_gl_js_version': settings.MAPBOX_GL_JS_VERSION,
        'mapbox_smd_style': settings.MAPBOX_SMD_STYLE,
    }


class HomeView(TemplateView):
    template_name = 'directory/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(mapbox_context())
        return context


class DistrictListView(TemplateView):
    template_name = 'directory/district_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        year = settings.CURRENT_REDISTRICTING_YEAR
        context['view'] = 'by_ward' if self.request.GET.get('view') == 'by_ward' else 'current'
        context['redistricting_year'] = year
        context['current_election_year'] = settings.CURRENT_ELECTION_YEAR

        if context['view'] == 'by_ward':
            context['wards'] = (
                Ward.objects.filter(redistricting_year=year)
                .prefetch_related('districts__anc')
                .order_by('ward_number')
            )
        else:
            ancs = ANC.objects.filter(redistricting_year=year).prefetch_related('districts').order_by('designator')
            # One query for every still-relevant term (current or future) across every district,
            # instead of one query per district (as _split_commissioner_terms does, fine for a
            # single ANC/ward but not for all 300+ districts on this page at once).
            today = timezone.localdate()
            terms_by_district = defaultdict(list)
            relevant_terms = (
                CommissionerTerm.objects.filter(district__redistricting_year=year, end_date__gte=today)
                .select_related('person')
            )
            for term in relevant_terms:
                terms_by_district[term.district_id].append(term)

            # Computed across ALL districts (not per ANC) so every ANC's table has identical
            # candidate columns and they stay lined up down the page.
            all_districts = [district for anc in ancs for district in anc.districts.all()]
            context['ballot_statuses'], context['vote_leaders_election'] = _attach_ballot_columns(all_districts)

            for anc in ancs:
                for district in anc.districts.all():
                    district_terms = terms_by_district.get(district.id, [])
                    current = [t for t in district_terms if t.is_current]
                    future = [t for t in district_terms if t.is_future]
                    district.current_term = resolve_current_commissioner_term(current)
                    district.future_term = future[0] if future else None
            context['ancs'] = ancs
        return context


def _attach_ballot_columns(districts):
    """Sets district.ballot_columns on each district: one list of current-election candidates per
    candidate status, in the same order as the returned list of statuses (ordered by display_order).
    Returns (statuses, election): election is the current Election when anyone in these districts
    is shown in bold as a vote leader (see _attach_vote_leaders), else None.
    Only statuses someone actually holds in these districts are included, so a column like
    "Write-In Candidate" appears once the first write-in is added and disappears when empty. Only
    candidates whose status is both published and counted are shown. Uses one query for all the
    districts passed in, rather than one per district."""
    districts = list(districts)
    on_ballot = list(
        Candidate.objects.filter(
            election__year=settings.CURRENT_ELECTION_YEAR,
            district__in=districts,
            status__publish_candidate=True,
            status__count_as_candidate=True,
        )
        .select_related('person', 'status')
        .order_by('person__full_name')
    )
    statuses = sorted({c.status for c in on_ballot}, key=lambda s: (s.display_order, s.name))
    by_district_and_status = defaultdict(list)
    for candidate in on_ballot:
        by_district_and_status[(candidate.district_id, candidate.status_id)].append(candidate)
    for district in districts:
        district.ballot_columns = [by_district_and_status.get((district.id, status.id), []) for status in statuses]
    return statuses, _attach_vote_leaders(districts, statuses)


def _attach_vote_leaders(districts, statuses):
    """Marks who is ahead in the current election's vote count, for bolding in the district table.

    Sets candidate.is_vote_leader on the leading candidate in district.ballot_columns, and
    district.write_in_leads to whether the combined write-in row is ahead. When it is,
    district.write_in_leads_column is the table column where "Write-in leads, name unknown" goes
    (None when it isn't, or when the table has no candidate columns at all). Before certification the leader is
    whoever ranks first; after, it's the certified winner (first place isn't always the winner).
    DCBOE only names write-in winners at certification, so a certified write-in win bolds the
    WriteInWinner's person instead of showing the "name unknown" text.

    Returns the current Election if any leader was found, else None, so pages can explain the bold."""
    for district in districts:
        district.write_in_leads = False
        district.write_in_leads_column = None
    results = list(
        ElectionResult.objects.filter(election__year=settings.CURRENT_ELECTION_YEAR, district__in=districts)
        .select_related('election')
    )
    if not results:
        return None
    election = results[0].election
    final = election.results_are_final
    leading_candidate_ids = set()
    write_in_leads_district_ids = set()
    for result in results:
        if not result.is_leader or result.votes == 0:
            continue
        if result.candidate_id:
            leading_candidate_ids.add(result.candidate_id)
        elif not final:
            write_in_leads_district_ids.add(result.district_id)
    leading_person_ids = set()
    if final:
        leading_person_ids = set(
            WriteInWinner.objects.filter(
                election__year=settings.CURRENT_ELECTION_YEAR, district__in=districts, person__isnull=False
            ).values_list('district_id', 'person_id')
        )

    # The text goes in the Write-In Candidate column when there is one, else the last column.
    write_in_column = next(
        (i for i, status in enumerate(statuses) if status.name == 'Write-In Candidate'),
        len(statuses) - 1 if statuses else None,
    )
    any_bold = False
    for district in districts:
        for candidates in district.ballot_columns:
            for candidate in candidates:
                candidate.is_vote_leader = (
                    candidate.id in leading_candidate_ids
                    or (district.id, candidate.person_id) in leading_person_ids
                )
        if district.id in write_in_leads_district_ids:
            district.write_in_leads = True
            district.write_in_leads_column = write_in_column
            any_bold = True
        any_bold = any_bold or any(c.is_vote_leader for candidates in district.ballot_columns for c in candidates)
    return election if any_bold else None


def _split_commissioner_terms(district):
    terms = list(district.commissioner_terms.select_related('person').order_by('start_date'))
    current_term = resolve_current_commissioner_term(t for t in terms if t.is_current)
    current_term_id = current_term.id if current_term else None

    current = []
    future = []
    former = []
    for term in terms:
        if term.id == current_term_id:
            current.append(term)
        elif term.is_future:
            future.append(term)
        else:
            former.append(term)
    former.sort(key=lambda t: t.start_date, reverse=True)
    return current, future, former


def _merge_consecutive_terms(terms, same_group_key):
    """terms must already be ordered by start_date ascending. Merges an unbroken run into one
    group when same_group_key matches on adjacent terms and one term's end_date equals the
    next term's start_date -- i.e. there's no gap between them."""
    groups = []
    for term in terms:
        last_group = groups[-1] if groups else None
        if (
            last_group
            and same_group_key(last_group[-1]) == same_group_key(term)
            and last_group[-1].end_date == term.start_date
        ):
            last_group.append(term)
        else:
            groups.append([term])
    return groups


def _term_group_row(group, current_term_id, **extra_fields):
    """Build a template-ready row summarizing a merged run of terms: combined date range,
    and status (current/future/former) derived from the run as a whole. current_term_id is the
    id of the one term (from resolve_current_commissioner_term) that should display as current
    for this district -- not just any term where is_current is True, since a same-day handoff
    briefly leaves two of those and only the incoming one should win."""
    first, last = group[0], group[-1]
    if any(t.id == current_term_id for t in group):
        status, css_class = 'current', 'term-current'
    elif last.is_future:
        status, css_class = 'future', 'term-future'
    else:
        status, css_class = 'former', ''

    start = (
        f'~{first.start_date.year}' if first.start_date_is_approximate
        else first.start_date.strftime('%B %-d, %Y')
    )
    return {
        'start_date': first.start_date,
        'end_date': last.end_date,
        'term_label': f'{start} to {last.end_date.strftime("%B %-d, %Y")}',
        'status': status,
        'css_class': css_class,
        **extra_fields,
    }


def _group_commissioner_terms(district):
    """Merge consecutive terms served by the same person in this district into a single row;
    non-consecutive stints -- the person left and later came back -- stay as separate rows."""
    terms = list(district.commissioner_terms.select_related('person').order_by('start_date'))
    current_term = resolve_current_commissioner_term(t for t in terms if t.is_current)
    current_term_id = current_term.id if current_term else None
    groups = _merge_consecutive_terms(terms, same_group_key=lambda t: t.person_id)

    rows = {'current': [], 'future': [], 'former': []}
    for group in groups:
        row = _term_group_row(group, current_term_id, person=group[0].person)
        rows[row['status']].append(row)

    rows['former'].sort(key=lambda r: r['end_date'], reverse=True)
    return rows['current'] + rows['future'] + rows['former']


def _group_terms_by_district(person):
    """Merge a person's consecutive terms in the same district into a single row; a stint in
    a different district, or a non-consecutive return to the same one, stays separate."""
    terms = list(person.commissioner_terms.select_related('district').order_by('start_date'))
    groups = _merge_consecutive_terms(terms, same_group_key=lambda t: t.district_id)
    rows = []
    for group in groups:
        district = group[0].district
        current_term = district.current_commissioner_term
        rows.append(_term_group_row(group, current_term.id if current_term else None, district=district))
    rows.sort(key=lambda r: r['start_date'], reverse=True)
    return rows


def _district_last_edited(district):
    """Most recent audit-trail change to any record tied to this district (commissioner terms,
    candidates, election results, write-in winners). None if nothing's been recorded yet -- the
    audit trail only covers changes made since django-simple-history was added, not the original
    legacy CSV import."""
    latest_dates = [
        history_manager.filter(district=district).order_by('-history_date').values_list('history_date', flat=True).first()
        for history_manager in (CommissionerTerm.history, Candidate.history, ElectionResult.history, WriteInWinner.history)
    ]
    latest_dates = [d for d in latest_dates if d]
    return max(latest_dates) if latest_dates else None


def _rcv_rows(contest):
    """A ranked-choice contest's tallies as (candidate rows, inactive ballots per round).

    Each candidate row has their votes per round (None after they were eliminated), the round
    they were last counted in, and their outcome. Rows run winner first, then by how many rounds
    each candidate lasted, then by their votes in their last round."""
    rounds = contest.num_rounds
    rows, inactive = {}, [None] * rounds
    for tally in contest.tallies.select_related('candidate__person'):
        if tally.is_inactive:
            inactive[tally.round_number - 1] = tally.votes
            continue
        row = rows.setdefault(tally.candidate_name_raw, {
            'name': tally.candidate_name_raw, 'candidate': tally.candidate,
            'votes': [None] * rounds, 'last_round': 0, 'outcome': '',
        })
        row['votes'][tally.round_number - 1] = tally.votes
        row['last_round'] = tally.round_number  # tallies come in round order
        if tally.outcome:
            row['outcome'] = tally.outcome
    ordered = sorted(rows.values(), key=lambda r: (
        r['outcome'] != RankedChoiceTally.OUTCOME_ELECTED, -r['last_round'], -r['votes'][r['last_round'] - 1],
    ))
    return ordered, inactive


def _rcv_table(contest, election):
    rows, inactive = _rcv_rows(contest)
    for row in rows:
        if row['outcome'] == RankedChoiceTally.OUTCOME_ELECTED:
            row['label'] = 'Won' if election.results_are_final else 'Leading'
        elif row['outcome'] == RankedChoiceTally.OUTCOME_ELIMINATED:
            row['label'] = f'Eliminated in round {row["last_round"]}'
        else:
            # Neither elected nor eliminated: still counted in the last round, but lost it.
            row['label'] = 'Runner-up' if election.results_are_final else 'Trailing'
    return {
        'contest': contest,
        'round_numbers': range(1, contest.num_rounds + 1),
        'rows': rows,
        'inactive': inactive,
        'winner': rows[0] if rows and rows[0]['outcome'] == RankedChoiceTally.OUTCOME_ELECTED else None,
    }


def _district_context(district):
    current_terms, future_terms, former_terms = _split_commissioner_terms(district)

    candidates_current = (
        district.candidates.filter(election__year=settings.CURRENT_ELECTION_YEAR)
        .select_related('person', 'status')
        .order_by('status__display_order', 'person__full_name')
    )

    results_by_election = []
    write_in_winners_by_year = {
        wiw.election.year: wiw for wiw in district.write_in_winners.select_related('election', 'person')
    }
    elections_with_results = {r.election for r in district.results.select_related('election')}
    rcv_contests = {c.election_id: c for c in district.rcv_contests.all()}
    for election in sorted(elections_with_results, key=lambda e: e.year, reverse=True):
        results = list(
            district.results.filter(election=election)
            .select_related('candidate__person')
            .order_by('ranking')
        )
        total_votes = sum(r.votes for r in results)
        for result in results:
            result.vote_share = result.votes / total_votes if total_votes else None
        leader = results[0] if results else None
        rcv_contest = rcv_contests.get(election.pk)
        results_by_election.append({
            'election': election,
            'rcv': _rcv_table(rcv_contest, election) if rcv_contest else None,
            'results': results,
            'total_votes': total_votes,
            'write_in_winner': write_in_winners_by_year.get(election.year),
            # A ranked-choice contest where nobody has more than half the first-choice votes is
            # decided by later rounds, so the first-choice leader may not win.
            # Certified, yet nobody won: the first-place candidate had withdrawn, so the seat was
            # left vacant (2022's 1E01, 6E08 and 7D10).
            'no_winner': election.results_are_final and bool(results) and not any(r.is_winner for r in results),
            'no_majority': (
                election.uses_ranked_choice and rcv_contest is None and len(results) > 1 and leader is not None
                and leader.votes * 2 <= total_votes
            ),
        })

    return {
        'district': district,
        'current_terms': current_terms,
        'future_terms': future_terms,
        'former_terms': former_terms,
        'commissioner_history': _group_commissioner_terms(district),
        'candidates_current': candidates_current,
        'results_by_election': results_by_election,
        'overlaps': district.overlaps_from.select_related('to_district').order_by('-overlap_percentage'),
        'neighbors': district.neighbors.order_by('designator'),
        'current_election_year': settings.CURRENT_ELECTION_YEAR,
        'last_edited': _district_last_edited(district),
    }


class DistrictDetailView(DetailView):
    model = District
    template_name = 'directory/district_detail.html'
    context_object_name = 'district'

    def get_object(self):
        return get_object_or_404(
            District, redistricting_year=self.kwargs['year'], designator=self.kwargs['designator']
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_district_context(self.object))
        context.update(mapbox_context())
        context['boundary_geometry'] = boundary_geometry(
            'district', self.object.designator, self.object.redistricting_year
        )
        context['district_designators'] = [self.object.designator]
        # Empty on purpose: the district page draws only this one SMD's fill, with no ANC
        # boundary line at all (an empty designator list never matches, so the line layer
        # renders nothing).
        context['anc_designators'] = []
        return context


def district_summary(request, year, designator):
    district = get_object_or_404(District, redistricting_year=year, designator=designator)
    context = _district_context(district)
    # Same vote-leader bolding as the district tables: reuse their logic on this one district.
    _, context['vote_leaders_election'] = _attach_ballot_columns([district])
    leader_ids = {c.id for column in district.ballot_columns for c in column if getattr(c, 'is_vote_leader', False)}
    context['candidates_current'] = list(context['candidates_current'])
    for candidate in context['candidates_current']:
        candidate.is_vote_leader = candidate.id in leader_ids
    context['write_in_leads'] = district.write_in_leads
    return render(request, 'directory/_district_summary.html', context)


# The JSON API and /llms.txt exist so AI assistants can answer "who is my ANC commissioner?"
# with one small request (issue 101). Responses are marked cacheable: the data only changes when
# local edits are pushed to production, so an hour's staleness is fine and saves repeat hits.
API_CACHE_SECONDS = 60 * 60
TEXT_CACHE_SECONDS = 24 * 60 * 60


def _api_response(data, status=200):
    response = JsonResponse(data, status=status, json_dumps_params={'indent': 2})
    response['Access-Control-Allow-Origin'] = '*'
    return response


def _person_json(request, term):
    if term is None:
        return None
    return {
        'name': term.person.full_name,
        'url': request.build_absolute_uri(term.person.get_absolute_url()),
        'term_start': term.start_date.isoformat(),
        'term_end': term.end_date.isoformat(),
    }


def _election_json(request, district):
    election = Election.objects.filter(year=settings.CURRENT_ELECTION_YEAR).first()
    if election is None:
        return None
    candidates = (
        district.candidates.filter(election=election, status__publish_candidate=True)
        .select_related('person', 'status')
        .order_by('status__display_order', 'person__full_name')
    )
    results = (
        district.results.filter(election=election)
        .select_related('candidate__person')
        .order_by('ranking')
    )
    return {
        'year': election.year,
        'date': election.election_date.isoformat() if election.election_date else None,
        'candidates': [
            {
                'name': c.person.full_name,
                'status': c.status.name,
                'url': request.build_absolute_uri(c.person.get_absolute_url()),
            }
            for c in candidates
        ],
        'results_status': election.results_status or None,
        'results_as_of': election.results_as_of.isoformat() if election.results_as_of else None,
        'results': [
            {
                'name': (r.candidate.person.full_name if r.candidate else r.candidate_name_raw) or 'Write-ins combined',
                'votes': r.votes,
                'is_winner': r.is_winner,
                'is_leading': r.is_leader,
            }
            for r in results
        ],
        'ranked_choice': _rcv_json(district.rcv_contests.filter(election=election).first()),
    }


def _rcv_json(contest):
    if contest is None:
        return None
    rows, inactive = _rcv_rows(contest)
    winner = rows[0] if rows and rows[0]['outcome'] == RankedChoiceTally.OUTCOME_ELECTED else None

    def name(row):
        return row['candidate'].person.full_name if row['candidate'] else row['name']

    return {
        'source': contest.release_name,
        'rcvis_url': contest.rcvis_url,
        'winner': name(winner) if winner else None,
        'rounds': [
            {
                'round': n,
                'votes': {name(r): r['votes'][n - 1] for r in rows if r['votes'][n - 1] is not None},
                'inactive_ballots': inactive[n - 1],
                'eliminated': [name(r) for r in rows if r['last_round'] == n
                               and r['outcome'] == RankedChoiceTally.OUTCOME_ELIMINATED],
                'elected': [name(r) for r in rows if r['last_round'] == n
                            and r['outcome'] == RankedChoiceTally.OUTCOME_ELECTED],
            }
            for n in range(1, contest.num_rounds + 1)
        ],
    }


def _district_json(request, district):
    current, future, _ = _split_commissioner_terms(district)
    anc = district.anc
    ward = district.ward
    return {
        'district': {
            'designator': district.designator,
            'name': f'Single Member District {district.designator}',
            'redistricting_year': district.redistricting_year,
            'url': request.build_absolute_uri(district.get_absolute_url()),
        },
        'anc': {
            'designator': anc.designator,
            'name': f'Advisory Neighborhood Commission {anc.designator}',
            'url': request.build_absolute_uri(anc.get_absolute_url()),
            'official_website': anc.dc_oanc_link or None,
        },
        'ward': {
            'number': ward.ward_number,
            'councilmember': ward.councilmember or None,
            'url': request.build_absolute_uri(ward.get_absolute_url()),
        },
        # null means the seat is vacant.
        'commissioner': _person_json(request, current[0] if current else None),
        'next_commissioner': _person_json(request, future[0] if future else None),
        'election': _election_json(request, district),
        'source': 'OpenANC (https://openanc.org/), an independent directory of DC ANC commissioners.',
    }


def _parse_coordinate(value, limit):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or not -limit <= number <= limit:
        return None
    return number


@count_in_goatcounter('API lookup')
@require_safe
@cache_control(public=True, max_age=API_CACHE_SECONDS)
def api_lookup(request):
    lat = _parse_coordinate(request.GET.get('lat'), 90)
    lng = _parse_coordinate(request.GET.get('lng', request.GET.get('lon')), 180)
    if lat is None or lng is None:
        return _api_response(
            {'error': 'Pass lat and lng as decimal degrees, e.g. /api/lookup/?lat=38.8977&lng=-77.0365'},
            status=400,
        )
    year = settings.CURRENT_REDISTRICTING_YEAR
    districts = {d.designator: d for d in District.objects.filter(redistricting_year=year).select_related('anc', 'ward')}
    designator = designator_at('district', sorted(districts), year, lng, lat)
    if designator is None:
        return _api_response(
            {'error': 'That point is not inside any DC Advisory Neighborhood Commission district.'},
            status=404,
        )
    return _api_response(_district_json(request, districts[designator]))


@count_in_goatcounter('API district')
@require_safe
@cache_control(public=True, max_age=API_CACHE_SECONDS)
def api_district(request, year, designator):
    district = (
        District.objects.filter(redistricting_year=year, designator=designator).select_related('anc', 'ward').first()
    )
    if district is None:
        return _api_response({'error': f'No district {designator} in the {year} redistricting.'}, status=404)
    return _api_response(_district_json(request, district))


@count_in_goatcounter('llms.txt')
@require_safe
@cache_control(public=True, max_age=TEXT_CACHE_SECONDS)
def llms_txt(request):
    context = {
        'base_url': request.build_absolute_uri('/').rstrip('/'),
        'redistricting_year': settings.CURRENT_REDISTRICTING_YEAR,
        'election_year': settings.CURRENT_ELECTION_YEAR,
    }
    return HttpResponse(render_to_string('directory/llms.txt', context), content_type='text/plain; charset=utf-8')


@require_safe
@cache_control(public=True, max_age=TEXT_CACHE_SECONDS)
def robots_txt(request):
    return HttpResponse(render_to_string('directory/robots.txt'), content_type='text/plain; charset=utf-8')


class ANCDetailView(DetailView):
    model = ANC
    template_name = 'directory/anc_detail.html'
    context_object_name = 'anc'

    def get_object(self):
        return get_object_or_404(ANC, redistricting_year=self.kwargs['year'], designator=self.kwargs['designator'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['districts'] = (
            self.object.districts.select_related('ward')
            .prefetch_related('commissioner_terms__person')
            .order_by('sort_order')
        )
        for district in context['districts']:
            current, future, former = _split_commissioner_terms(district)
            district.current_term = current[0] if current else None
            district.future_term = future[0] if future else None
        context['ballot_statuses'], context['vote_leaders_election'] = _attach_ballot_columns(context['districts'])
        context['links'] = self.object.links.filter(publish=True)
        context['overlaps'] = self.object.overlaps_from.select_related('to_anc').order_by('-overlap_percentage')
        context.update(mapbox_context())
        context['boundary_geometry'] = boundary_geometry('anc', self.object.designator, self.object.redistricting_year)
        context['district_designators'] = [district.designator for district in context['districts']]
        context['anc_designators'] = [self.object.designator]
        return context


class WardDetailView(DetailView):
    model = Ward
    template_name = 'directory/ward_detail.html'
    context_object_name = 'ward'

    def get_object(self):
        return get_object_or_404(Ward, redistricting_year=self.kwargs['year'], ward_number=self.kwargs['number'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['districts'] = (
            self.object.districts.select_related('anc')
            .prefetch_related('commissioner_terms__person')
            .order_by('sort_order')
        )
        for district in context['districts']:
            current, future, former = _split_commissioner_terms(district)
            district.current_term = current[0] if current else None
            district.future_term = future[0] if future else None
        context['ballot_statuses'], context['vote_leaders_election'] = _attach_ballot_columns(context['districts'])
        context.update(mapbox_context())
        context['boundary_geometry'] = boundary_geometry('ward', self.object.ward_number, self.object.redistricting_year)
        context['district_designators'] = [district.designator for district in context['districts']]
        context['anc_designators'] = sorted({district.anc.designator for district in context['districts']})
        return context


class PersonListView(ListView):
    model = Person
    template_name = 'directory/person_list.html'
    context_object_name = 'people'

    def get_queryset(self):
        return (
            Person.objects.filter(Q(commissioner_terms__isnull=False) | Q(candidacies__isnull=False))
            .distinct()
            .order_by('full_name')
            .prefetch_related('aliases')
        )


class PersonDetailView(DetailView):
    model = Person
    template_name = 'directory/person_detail.html'
    context_object_name = 'person'
    slug_field = 'slug'

    def get(self, request, *args, **kwargs):
        # A merged-away person's old URL permanently redirects to the person they were merged into.
        if not Person.objects.filter(slug=kwargs['slug']).exists():
            redirect_row = PersonSlugRedirect.objects.select_related('person').filter(slug=kwargs['slug']).first()
            if redirect_row:
                return redirect(redirect_row.person, permanent=True)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['commissioner_terms'] = _group_terms_by_district(self.object)
        context['links'] = self.object.links.filter(publish=True)
        candidacies = (
            self.object.candidacies.select_related('district', 'election', 'status')
            .order_by('-election__year')
        )
        # attach each candidacy's own result row (votes/ranking), if the election has been decided
        result_lookup = {
            r.candidate_id: r
            for r in ElectionResult.objects.filter(candidate__person=self.object).select_related('election')
        }
        # Write-in winners have no result row of their own (DCBOE only reports write-ins combined).
        write_in_wins = set(self.object.write_in_wins.values_list('election_id', 'district_id'))
        rcv_rounds = {
            (c.election_id, c.district_id): c.num_rounds
            for c in RankedChoiceContest.objects.filter(district__candidates__person=self.object).distinct()
        }
        for candidacy in candidacies:
            candidacy.result = result_lookup.get(candidacy.id)
            if candidacy.result:
                candidacy.result_label = candidacy.result.outcome_label
                rounds = rcv_rounds.get((candidacy.election_id, candidacy.district_id), 1)
                if candidacy.result_label and rounds > 1:
                    candidacy.result_label += f' after {rounds} ranked-choice rounds'
            elif (candidacy.election_id, candidacy.district_id) in write_in_wins:
                candidacy.result_label = 'Won (write-in)'
            else:
                candidacy.result_label = ''
        context['candidacies'] = candidacies
        return context


class AboutView(TemplateView):
    template_name = 'directory/about.html'


class UpdatesView(ListView):
    model = SiteUpdate
    template_name = 'directory/updates.html'
    context_object_name = 'updates'

    def get_queryset(self):
        return SiteUpdate.objects.filter(is_published=True)


def _districts_with_active_candidate_counts():
    """Current-cycle districts, each annotated with active_candidate_count: how many candidates it
    has in the current election whose status has Count as Candidate checked."""
    return District.objects.filter(redistricting_year=settings.CURRENT_REDISTRICTING_YEAR).annotate(
        active_candidate_count=Count(
            'candidates',
            filter=Q(
                candidates__election__year=settings.CURRENT_ELECTION_YEAR,
                candidates__status__count_as_candidate=True,
            ),
        )
    )


def _candidate_bucket(count):
    if count == 0:
        return 'no_candidates'
    if count == 1:
        return 'one_candidate'
    return 'two_plus_candidates'


class CountsView(TemplateView):
    template_name = 'directory/counts.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        year = settings.CURRENT_REDISTRICTING_YEAR
        election_year = settings.CURRENT_ELECTION_YEAR
        today = timezone.localdate()

        # -- candidates by status, current election -------------------------------------
        status_counts = (
            CandidateStatus.objects.annotate(
                candidate_count=Count('candidates', filter=Q(candidates__election__year=election_year))
            )
            .filter(candidate_count__gt=0)
            .order_by('display_order')
        )
        status_totals = {
            'active': sum(s.candidate_count for s in status_counts if s.count_as_candidate),
            'inactive': sum(s.candidate_count for s in status_counts if not s.count_as_candidate),
        }

        # -- contested districts, current cycle ------------------------------------------
        districts = _districts_with_active_candidate_counts().select_related('anc', 'ward')

        dc_totals = {'no_candidates': 0, 'one_candidate': 0, 'two_plus_candidates': 0, 'total': 0}
        by_ward = {}
        by_anc = {}
        for district in districts:
            key = _candidate_bucket(district.active_candidate_count)
            dc_totals[key] += 1
            dc_totals['total'] += 1

            ward_row = by_ward.setdefault(
                district.ward, {'no_candidates': 0, 'one_candidate': 0, 'two_plus_candidates': 0, 'total': 0}
            )
            ward_row[key] += 1
            ward_row['total'] += 1

            anc_row = by_anc.setdefault(
                district.anc, {'no_candidates': 0, 'one_candidate': 0, 'two_plus_candidates': 0, 'total': 0}
            )
            anc_row[key] += 1
            anc_row['total'] += 1

        for anc_row in by_anc.values():
            anc_row['mostly_uncontested'] = anc_row['no_candidates'] / anc_row['total'] >= 0.5

        # -- commissioner vacancies, current cycle ---------------------------------------
        total_districts = District.objects.filter(redistricting_year=year).count()
        # Count districts, not terms: a same-day handoff (one term ending today, the next
        # starting today) briefly leaves two terms matching "current" for the same district,
        # which would otherwise double-count it and could even push vacancies negative.
        filled = CommissionerTerm.objects.filter(
            district__redistricting_year=year, start_date__lte=today, end_date__gte=today
        ).values('district').distinct().count()

        context.update({
            'election_year': election_year,
            'status_counts': status_counts,
            'status_totals': status_totals,
            'dc_totals': dc_totals,
            'by_ward': sorted(by_ward.items(), key=lambda pair: pair[0].ward_number),
            'by_anc': sorted(by_anc.items(), key=lambda pair: pair[0].designator),
            'total_districts': total_districts,
            'vacancies': total_districts - filled,
        })
        return context


class SuggestionCreateView(CreateView):
    model = Suggestion
    form_class = SuggestionForm
    template_name = 'directory/suggest_edit.html'
    success_url = reverse_lazy('directory:suggest_edit')

    def get_initial(self):
        initial = super().get_initial()
        district_id = self.request.GET.get('district')
        person_id = self.request.GET.get('person')
        if district_id:
            initial['district'] = district_id
        if person_id:
            initial['person'] = person_id
        return initial

    def form_valid(self, form):
        if form.is_spam():
            # Silently discard -- don't tip off the bot, don't save, still say thanks.
            logger.info('Dropped spam suggestion (%s)', form.spam_reason)
            messages.success(self.request, 'Thanks! Your suggestion has been submitted for review.')
            return redirect(self.success_url)
        response = super().form_valid(form)
        self._notify(self.object)
        messages.success(self.request, 'Thanks! Your suggestion has been submitted for review.')
        return response

    def _notify(self, suggestion):
        subject = f'OpenANC suggestion #{suggestion.pk}'
        lines = [f'From: {suggestion.name or "(no name)"} <{suggestion.email or "no email"}>']
        if suggestion.district:
            lines.append(f'District: {suggestion.district}')
        if suggestion.person:
            lines.append(f'Person: {suggestion.person}')
        if suggestion.link:
            lines.append(f'Link: {suggestion.link}')
        lines += ['', suggestion.message, '', self.request.build_absolute_uri(
            reverse_lazy('admin:directory_suggestion_change', args=[suggestion.pk])
        )]
        # A mail failure shouldn't lose the suggestion (it's already saved), but log it so a
        # broken SMTP setup shows up in `flyctl logs` instead of failing silently.
        try:
            send_mail(
                subject,
                '\n'.join(lines),
                settings.DEFAULT_FROM_EMAIL,
                [settings.SUGGESTION_NOTIFICATION_EMAIL],
            )
        except Exception:
            logger.exception('Failed to send notification email for suggestion #%s', suggestion.pk)


class ContestedMapView(TemplateView):
    template_name = 'directory/contested.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(mapbox_context())
        # Which districts to show for each filter option, computed live from the database
        # (current election, statuses with Count as Candidate checked) so the map never goes
        # stale the way a hand-uploaded Mapbox tileset property would.
        designators_by_bucket = {'no_candidates': [], 'one_candidate': [], 'two_plus_candidates': []}
        for district in _districts_with_active_candidate_counts().order_by('designator'):
            designators_by_bucket[_candidate_bucket(district.active_candidate_count)].append(district.designator)
        context['designators_by_bucket'] = designators_by_bucket
        context['redistricting_year'] = settings.CURRENT_REDISTRICTING_YEAR
        return context
