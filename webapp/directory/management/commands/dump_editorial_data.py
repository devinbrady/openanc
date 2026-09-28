"""Run LOCALLY. Exports every "editorial" model (see directory/sync.py) to a JSON fixture, plus
a small manifest of which primary keys exist for each model -- used by load_editorial_data's
--prune-manifest to catch rows that were deleted locally so they don't linger on production
forever (plain loaddata only ever inserts/updates, never deletes).

Usage: python manage.py dump_editorial_data --output editorial.json --manifest manifest.json
"""
import json

from django.apps import apps
from django.core.management import call_command
from django.core.management.base import BaseCommand

from directory.sync import EDITORIAL_MODELS


class Command(BaseCommand):
    help = "Export editorial data to a JSON fixture for pushing to production."

    def add_arguments(self, parser):
        parser.add_argument('--output', required=True, help='Path to write the data fixture to.')
        parser.add_argument('--manifest', required=True, help='Path to write the PK manifest to.')

    def handle(self, *args, **options):
        call_command(
            'dumpdata', *EDITORIAL_MODELS,
            indent=2, output=options['output'],
        )
        self.stdout.write(self.style.SUCCESS(f"Wrote data fixture: {options['output']}"))

        manifest = {}
        for label in EDITORIAL_MODELS:
            model = apps.get_model(label)
            manifest[label] = list(model.objects.values_list('pk', flat=True))
        with open(options['manifest'], 'w') as f:
            json.dump(manifest, f, indent=2)
        self.stdout.write(self.style.SUCCESS(f"Wrote PK manifest: {options['manifest']}"))
