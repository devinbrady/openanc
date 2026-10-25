"""Drafts a SiteUpdate summarizing recent changes to commissioner terms, candidates, write-in
winners, and new people -- mined from the django-simple-history audit trail (see models.py).
Creates one unpublished (is_published=False) SiteUpdate for a human to review, edit, and publish
by hand in the admin. This is a draft generator, not a finished-prose generator -- expect to
tidy the wording before publishing.

Usage:
  python manage.py draft_site_update                  # since the last published update, through today
  python manage.py draft_site_update --since 2026-09-01 --date 2026-09-27
"""
import datetime
from collections import Counter

from django.core.management.base import BaseCommand
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from directory.models import Candidate, CandidateStatus, CommissionerTerm, Person, SiteUpdate, WriteInWinner

# Summary-table row labels for candidate statuses; any status not listed falls back to
# "Candidates: <status>".
STATUS_LABELS = {
    'Won': 'Winning candidates',
    'Lost': 'Losing candidates',
    'On the Ballot': 'Candidates on the ballot',
    'Filed Signatures': 'Candidates who filed signatures',
    'Write-In Candidate': 'Write-in candidates',
    'Pulled Papers for Ballot': 'Candidates who pulled papers',
    'Declared Intention to Run': 'Declared candidates',
    'Withdrew': 'Withdrawn candidates',
    'Did Not Qualify for Ballot': 'Candidates who did not qualify',
}


def _parse_date(value):
    return datetime.date.fromisoformat(value)


def _link(obj):
    return format_html('<a href="{}">{}</a>', obj.get_absolute_url(), obj)


class Command(BaseCommand):
    help = "Draft a SiteUpdate from recent audit-trail history. Creates it unpublished for review."

    def add_arguments(self, parser):
        parser.add_argument('--date', type=_parse_date, default=None, help='The update date (default: today).')
        parser.add_argument(
            '--since', type=_parse_date, default=None,
            help="Start of the window (default: the last published update's date).",
        )

    def handle(self, *args, **options):
        as_of = options['date'] or datetime.date.today()
        since = options['since']
        if since is None:
            last = SiteUpdate.objects.filter(is_published=True).order_by('-date').first()
            since = last.date if last else as_of

        sections = [
            ('Commissioner changes', self._commissioner_term_lines(since, as_of)),
            ('Candidate changes', self._candidate_lines(since, as_of)),
            ('Write-in winners certified', self._write_in_winner_lines(since, as_of)),
            ('New people added', self._new_person_lines(since, as_of)),
        ]
        sections = [(heading, lines) for heading, lines in sections if lines]

        if not sections:
            self.stdout.write('No tracked changes found in that window -- no draft created.')
            return

        body_parts = [f'<p>Changes from {since.isoformat()} to {as_of.isoformat()}:</p>']
        for heading, lines in sections:
            body_parts.append(f'<p><strong>{heading}</strong></p>')
            body_parts.append('<ul>')
            body_parts.extend(f'<li>{line}</li>' for line in lines)
            body_parts.append('</ul>')
        body_parts.extend(self._summary_table(since, as_of))

        update = SiteUpdate.objects.create(date=as_of, body='\n'.join(body_parts), is_published=False)
        self.stdout.write(self.style.SUCCESS(f'Created draft SiteUpdate #{update.pk} for {as_of} (unpublished).'))

    def _in_window(self, history_manager, since, as_of):
        return history_manager.filter(history_date__date__gte=since, history_date__date__lte=as_of).order_by('history_date')

    def _commissioner_term_lines(self, since, as_of):
        lines = []
        for record in self._in_window(CommissionerTerm.history, since, as_of):
            try:
                if record.history_type == '+':
                    lines.append(f'{_link(record.district)}: {_link(record.person)} appointed commissioner (term starts {record.start_date}).')
                elif record.history_type == '~':
                    prev = record.prev_record
                    if prev and prev.end_date != record.end_date:
                        lines.append(f"{_link(record.district)}: {_link(record.person)}'s term now ends {record.end_date} (was {prev.end_date}).")
                elif record.history_type == '-':
                    lines.append(f"{_link(record.district)}: {_link(record.person)}'s commissioner term record was removed.")
            except Exception:
                continue
        return lines

    def _candidate_lines(self, since, as_of):
        lines = []
        for record in self._in_window(Candidate.history, since, as_of):
            try:
                if record.history_type == '+':
                    lines.append(
                        f'{_link(record.district)}: {_link(record.person)} added as a candidate '
                        f'(election year {record.election.year}, status: {record.status}).'
                    )
                elif record.history_type == '~':
                    prev = record.prev_record
                    if prev and prev.status_id != record.status_id:
                        lines.append(
                            f"{_link(record.district)}: {_link(record.person)}'s candidate status changed to "
                            f"{record.status} (election year {record.election.year})."
                        )
            except Exception:
                continue
        return lines

    def _write_in_winner_lines(self, since, as_of):
        lines = []
        for record in self._in_window(WriteInWinner.history, since, as_of):
            try:
                if record.history_type == '+':
                    name = _link(record.person) if record.person else format_html('{}', record.candidate_name_raw)
                    lines.append(f'{_link(record.district)}: {name} certified as write-in winner (election year {record.election.year}).')
            except Exception:
                continue
        return lines

    def _new_person_lines(self, since, as_of):
        lines = []
        # Skip people deleted since (merged duplicates etc.) -- their page link would be dead.
        records = self._in_window(Person.history, since, as_of).filter(history_type='+', id__in=Person.objects.values('pk'))
        for record in records:
            lines.append(format_html('<a href="{}">{}</a>', reverse('directory:person_detail', kwargs={'slug': record.slug}), record.full_name))
        return lines

    def _summary_table(self, since, as_of):
        """Rows of Old/Diff/New counts for whatever changed, comparing the database as it stood
        at the start of `since` with the end of `as_of`. Candidate counts are broken out by status
        and limited to the elections touched in the window."""
        tz = timezone.get_current_timezone()
        start = datetime.datetime.combine(since, datetime.time.min, tzinfo=tz)
        end = datetime.datetime.combine(as_of + datetime.timedelta(days=1), datetime.time.min, tzinfo=tz)

        rows = []
        election_ids = set(self._in_window(Candidate.history, since, as_of).values_list('election_id', flat=True))
        if election_ids:
            def status_counts(moment):
                return Counter(
                    Candidate.history.as_of(moment).filter(election_id__in=election_ids).values_list('status_id', flat=True)
                )
            old_counts, new_counts = status_counts(start), status_counts(end)
            for status in CandidateStatus.objects.filter(publish_candidate=True):
                rows.append((STATUS_LABELS.get(status.name, f'Candidates: {status.name}'), old_counts[status.pk], new_counts[status.pk]))

        for label, model in [('Commissioner terms', CommissionerTerm), ('Write-in winners', WriteInWinner), ('People', Person)]:
            rows.append((label, model.history.as_of(start).count(), model.history.as_of(end).count()))

        rows = [(label, old, new) for label, old, new in rows if old != new]
        if not rows:
            return []
        parts = ['<table>', '<tr><th>Type</th><th>Old</th><th>Diff</th><th>New</th></tr>']
        parts.extend(
            format_html('<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>', label, old, f'{new - old:+d}', new)
            for label, old, new in rows
        )
        parts.append('</table>')
        return parts
