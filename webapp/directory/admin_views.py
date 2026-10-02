"""Custom admin pages for the person-import/matching tool -- wired into PersonAdmin.get_urls()
in admin.py. Replaces the old scripts/match_people.py CSV-round-trip: upload a CSV, review
fuzzy-matched candidates in the browser, apply the decisions.
"""
import csv
import datetime
import io

from django.conf import settings
from django.contrib import admin, messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from simple_history.utils import update_change_reason

from .forms import PersonImportUploadForm
from .matching import match_person_rows
from .models import Candidate, CommissionerTerm, District, Person, PersonImportBatch, PersonImportRow


# Column names seen in the wild for the SMD designator, in order of preference: a plain
# "district" header if the CSV was built for this tool, otherwise whatever DCBOE's own exports
# use -- e.g. data/dcboe/excel-clean/*.csv has "ANC-SMD" (see scripts/process_candidates.py,
# which recognizes the same variants for the legacy pipeline).
DISTRICT_COLUMN_ALIASES = ['district', 'anc-smd', 'anc/smd', 'smd', 'office']


def _parse_csv(uploaded_file):
    """Returns a list of (name, district_designator) tuples. Raises ValueError if there's no
    'name' column."""
    text = uploaded_file.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text))
    columns = {(name or '').strip().lower(): name for name in (reader.fieldnames or [])}
    name_col = columns.get('name')
    if not name_col:
        raise ValueError("CSV must have a 'name' column (and optionally a 'district' column).")
    district_col = next((columns[alias] for alias in DISTRICT_COLUMN_ALIASES if alias in columns), None)

    rows = []
    for raw_row in reader:
        name = (raw_row.get(name_col) or '').strip()
        if not name:
            continue
        designator = (raw_row.get(district_col) or '').strip() if district_col else ''
        rows.append((name, designator))
    return rows


def person_import_upload(request):
    if request.method == 'POST':
        form = PersonImportUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                rows_data = _parse_csv(form.cleaned_data['csv_file'])
            except ValueError as e:
                form.add_error('csv_file', str(e))
            else:
                if not rows_data:
                    form.add_error('csv_file', 'No rows with a name found in that file.')
                else:
                    batch = PersonImportBatch.objects.create(
                        source_label=form.cleaned_data['source_label'],
                        election=form.cleaned_data['election'],
                        default_status=form.cleaned_data['default_status'],
                    )
                    districts_by_designator = {
                        d.designator: d
                        for d in District.objects.filter(redistricting_year=settings.CURRENT_REDISTRICTING_YEAR)
                    }
                    PersonImportRow.objects.bulk_create([
                        PersonImportRow(
                            batch=batch,
                            raw_name=name,
                            raw_district_designator=designator,
                            district=districts_by_designator.get(designator),
                        )
                        for name, designator in rows_data
                    ])
                    match_person_rows(batch)
                    messages.success(request, f'Imported {len(rows_data)} row(s) into batch #{batch.pk}.')
                    return redirect('admin:directory_person_import_review', batch_id=batch.pk)
    else:
        form = PersonImportUploadForm()

    context = {
        **admin.site.each_context(request),
        'title': 'Import candidates',
        'form': form,
        'opts': Person._meta,
    }
    return TemplateResponse(request, 'admin/directory/person_import/upload.html', context)


def _most_recent_designators(person_ids):
    """{person_id: SMD designator} for each person's most recent commissioner term or candidacy,
    whichever is later. A candidacy is dated by its election date (falling back to Nov 1 of the
    election year when that isn't recorded). People with neither get no entry."""
    latest = {}

    def consider(person_id, when, designator):
        if person_id not in latest or when > latest[person_id][0]:
            latest[person_id] = (when, designator)

    for term in CommissionerTerm.objects.filter(person_id__in=person_ids).select_related('district'):
        consider(term.person_id, term.start_date, term.district.designator)
    for candidacy in Candidate.objects.filter(person_id__in=person_ids).select_related('district', 'election'):
        when = candidacy.election.election_date or datetime.date(candidacy.election.year, 11, 1)
        consider(candidacy.person_id, when, candidacy.district.designator)
    return {person_id: designator for person_id, (_, designator) in latest.items()}


def person_import_review(request, batch_id):
    batch = get_object_or_404(PersonImportBatch, pk=batch_id)
    rows = list(batch.rows.select_related('district', 'chosen_person').all())

    if request.method == 'POST':
        valid_decisions = dict(PersonImportRow.DECISION_CHOICES)
        for row in rows:
            decision = request.POST.get(f'decision_{row.id}')
            if decision not in valid_decisions:
                continue
            row.decision = decision
            if decision == PersonImportRow.DECISION_LINK:
                person_id = request.POST.get(f'person_{row.id}') or None
                row.chosen_person_id = person_id
            else:
                row.chosen_person = None
            row.save()
        messages.success(request, 'Decisions saved.')
        return redirect('admin:directory_person_import_review', batch_id=batch.pk)

    designators = _most_recent_designators({c['person_id'] for row in rows for c in row.match_candidates_json})
    for row in rows:
        for candidate in row.match_candidates_json:
            designator = designators.get(candidate['person_id'])
            candidate['label'] = f"{candidate['full_name']} ({designator})" if designator else candidate['full_name']

    context = {
        **admin.site.each_context(request),
        'title': f'Review import batch #{batch.pk}',
        'batch': batch,
        'rows': rows,
        'opts': Person._meta,
    }
    return TemplateResponse(request, 'admin/directory/person_import/review.html', context)


def person_import_apply(request, batch_id):
    batch = get_object_or_404(PersonImportBatch, pk=batch_id)
    if request.method != 'POST':
        return redirect('admin:directory_person_import_review', batch_id=batch.pk)

    created_people = 0
    created_candidates = 0
    pending_count = 0
    incomplete_count = 0

    with transaction.atomic():
        for row in batch.rows.filter(applied=False):
            if row.decision == PersonImportRow.DECISION_SKIP:
                row.applied = True
                row.save()
                continue
            if row.decision == PersonImportRow.DECISION_PENDING:
                pending_count += 1
                continue
            if not row.district or not batch.election or not batch.default_status:
                incomplete_count += 1
                continue

            if row.decision == PersonImportRow.DECISION_NEW:
                person = Person.objects.create(full_name=row.raw_name)
                update_change_reason(person, f'Import batch #{batch.pk}: {batch.source_label}'.strip())
                created_people += 1
            else:
                if not row.chosen_person_id:
                    incomplete_count += 1
                    continue
                person = row.chosen_person

            candidate, created = Candidate.objects.get_or_create(
                person=person, election=batch.election,
                defaults={'district': row.district, 'status': batch.default_status, 'source': 'import'},
            )
            if created:
                update_change_reason(candidate, f'Import batch #{batch.pk}: {batch.source_label}'.strip())
                created_candidates += 1

            row.chosen_person = person
            row.applied = True
            row.save()

    if pending_count:
        messages.warning(request, f'{pending_count} row(s) still need a decision -- go back and choose link/new/skip for those.')
    if incomplete_count:
        messages.warning(request, f'{incomplete_count} row(s) could not be applied (missing district, election, or default status).')
    messages.success(request, f'Applied batch #{batch.pk}: {created_people} new people, {created_candidates} new candidates.')
    return redirect('admin:directory_person_import_review', batch_id=batch.pk)
