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

from django.core.management.base import BaseCommand

from directory.models import Candidate, CommissionerTerm, Person, SiteUpdate, WriteInWinner


def _parse_date(value):
    return datetime.date.fromisoformat(value)


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

        update = SiteUpdate.objects.create(date=as_of, body='\n'.join(body_parts), is_published=False)
        self.stdout.write(self.style.SUCCESS(f'Created draft SiteUpdate #{update.pk} for {as_of} (unpublished).'))

    def _in_window(self, history_manager, since, as_of):
        return history_manager.filter(history_date__date__gte=since, history_date__date__lte=as_of).order_by('history_date')

    def _commissioner_term_lines(self, since, as_of):
        lines = []
        for record in self._in_window(CommissionerTerm.history, since, as_of):
            try:
                if record.history_type == '+':
                    lines.append(f'{record.district}: {record.person} appointed commissioner (term starts {record.start_date}).')
                elif record.history_type == '~':
                    prev = record.prev_record
                    if prev and prev.end_date != record.end_date:
                        lines.append(f"{record.district}: {record.person}'s term now ends {record.end_date} (was {prev.end_date}).")
                elif record.history_type == '-':
                    lines.append(f"{record.district}: {record.person}'s commissioner term record was removed.")
            except Exception:
                continue
        return lines

    def _candidate_lines(self, since, as_of):
        lines = []
        for record in self._in_window(Candidate.history, since, as_of):
            try:
                if record.history_type == '+':
                    lines.append(f'{record.district}: {record.person} declared as a candidate ({record.election.year}, status: {record.status}).')
                elif record.history_type == '~':
                    prev = record.prev_record
                    if prev and prev.status_id != record.status_id:
                        lines.append(f"{record.district}: {record.person}'s candidate status changed to {record.status} ({record.election.year}).")
            except Exception:
                continue
        return lines

    def _write_in_winner_lines(self, since, as_of):
        lines = []
        for record in self._in_window(WriteInWinner.history, since, as_of):
            try:
                if record.history_type == '+':
                    name = record.person or record.candidate_name_raw
                    lines.append(f'{record.district}: {name} certified as write-in winner ({record.election.year}).')
            except Exception:
                continue
        return lines

    def _new_person_lines(self, since, as_of):
        lines = []
        for record in self._in_window(Person.history, since, as_of).filter(history_type='+'):
            lines.append(str(record.full_name))
        return lines
