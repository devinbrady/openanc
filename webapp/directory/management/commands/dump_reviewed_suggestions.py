"""Run LOCALLY. Exports every Suggestion the user has already reviewed (status no longer
"pending") to a JSON fixture, for pushing back to production. Safe as a plain loaddata target on
production: every one of these rows originated there, so this only ever updates
status/moderator_notes/etc on rows at or below the last pull's high-water mark -- any newer
submissions (higher PKs) that arrived on production since are untouched.

Usage: python manage.py dump_reviewed_suggestions --output suggestions_reviewed.json
"""
from django.core import serializers
from django.core.management.base import BaseCommand

from directory.models import Suggestion


class Command(BaseCommand):
    help = "Export reviewed (non-pending) Suggestion rows to a JSON fixture."

    def add_arguments(self, parser):
        parser.add_argument('--output', required=True)

    def handle(self, *args, **options):
        queryset = Suggestion.objects.exclude(status=Suggestion.STATUS_PENDING).order_by('pk')
        data = serializers.serialize('json', queryset, indent=2)
        with open(options['output'], 'w') as f:
            f.write(data)
        self.stdout.write(self.style.SUCCESS(f"Wrote {queryset.count()} reviewed suggestion(s) to {options['output']}"))
