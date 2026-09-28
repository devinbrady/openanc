"""Run ON PRODUCTION (invoked remotely by ops/sync_production.sh's `pull-suggestions`). Serializes
every Suggestion submitted since the given primary key -- i.e. the ones the public form has
collected on production since the last pull -- so they can be loaded into the local database for
review. Prints pure JSON to stdout (no log noise) so the caller can capture it directly.

Usage: python manage.py dump_new_suggestions --since-id 42
"""
from django.core import serializers
from django.core.management.base import BaseCommand

from directory.models import Suggestion


class Command(BaseCommand):
    help = "Serialize Suggestion rows newer than --since-id to stdout as JSON. Run on production."

    def add_arguments(self, parser):
        parser.add_argument('--since-id', type=int, default=0)

    def handle(self, *args, **options):
        queryset = Suggestion.objects.filter(pk__gt=options['since_id']).order_by('pk')
        return serializers.serialize('json', queryset, indent=2)
