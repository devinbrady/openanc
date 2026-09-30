from collections import defaultdict

from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import DetailView, ListView, TemplateView
from django.views.generic.edit import CreateView

from .boundaries import boundary_geometry
from .forms import SuggestionForm
from .models import (
    ANC,
    Candidate,
    CandidateStatus,
    CommissionerTerm,
    District,
    ElectionResult,
    Person,
    SiteUpdate,
    Suggestion,
    Ward,
    WriteInWinner,
    resolve_current_commissioner_term,
)


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
            for anc in ancs:
                for district in anc.districts.all():
                    district_terms = terms_by_district.get(district.id, [])
                    current = [t for t in district_terms if t.is_current]
                    future = [t for t in district_terms if t.is_future]
                    district.current_term = resolve_current_commissioner_term(current)
                    district.future_term = future[0] if future else None
            context['ancs'] = ancs
        return context


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
    for election in sorted(elections_with_results, key=lambda e: e.year, reverse=True):
        results = (
            district.results.filter(election=election)
            .select_related('candidate__person')
            .order_by('ranking')
        )
        results_by_election.append({
            'election': election,
            'results': results,
            'write_in_winner': write_in_winners_by_year.get(election.year),
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
    return render(request, 'directory/_district_summary.html', context)


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
        )


class PersonDetailView(DetailView):
    model = Person
    template_name = 'directory/person_detail.html'
    context_object_name = 'person'
    slug_field = 'slug'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['commissioner_terms'] = _group_terms_by_district(self.object)
        candidacies = (
            self.object.candidacies.select_related('district', 'election', 'status')
            .order_by('-election__year')
        )
        # attach each candidacy's own result row (votes/ranking), if the election has been decided
        result_lookup = {r.candidate_id: r for r in ElectionResult.objects.filter(candidate__person=self.object)}
        for candidacy in candidacies:
            candidacy.result = result_lookup.get(candidacy.id)
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

        # -- contested districts, current cycle ------------------------------------------
        districts = District.objects.filter(redistricting_year=year).annotate(
            active_candidate_count=Count(
                'candidates',
                filter=Q(
                    candidates__election__year=election_year,
                    candidates__status__count_as_candidate=True,
                ),
            )
        ).select_related('anc', 'ward')

        def bucket(count):
            if count == 0:
                return 'no_candidates'
            if count == 1:
                return 'one_candidate'
            return 'two_plus_candidates'

        dc_totals = {'no_candidates': 0, 'one_candidate': 0, 'two_plus_candidates': 0}
        by_ward = {}
        by_anc = {}
        for district in districts:
            key = bucket(district.active_candidate_count)
            dc_totals[key] += 1

            ward_row = by_ward.setdefault(
                district.ward, {'no_candidates': 0, 'one_candidate': 0, 'two_plus_candidates': 0}
            )
            ward_row[key] += 1

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
        lines += ['', suggestion.message, '', self.request.build_absolute_uri(
            reverse_lazy('admin:directory_suggestion_change', args=[suggestion.pk])
        )]
        send_mail(
            subject,
            '\n'.join(lines),
            settings.DEFAULT_FROM_EMAIL,
            [settings.SUGGESTION_NOTIFICATION_EMAIL],
            fail_silently=True,
        )


class ContestedMapView(TemplateView):
    template_name = 'directory/contested.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(mapbox_context())
        context['contested_styles'] = settings.MAPBOX_CONTESTED_STYLES
        return context
