"""Prints one editorial model's rows as JSON ({pk: {field: value}}), for drilling into a table
whose content hash differs between local and production (see ops/sync_production.sh status).
Usage: python manage.py editorial_rows directory.Candidate
"""
import json

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError

from directory.sync import EDITORIAL_MODELS, normalized_rows


class Command(BaseCommand):
    help = "Print one editorial model's rows as JSON, keyed by primary key."

    def add_arguments(self, parser):
        parser.add_argument('model', help='An editorial model label, e.g. directory.Candidate.')

    def handle(self, *args, **options):
        label = options['model']
        if label not in EDITORIAL_MODELS:
            raise CommandError(f'{label} is not an editorial model.')
        rows = {str(r['pk']): r['fields'] for r in normalized_rows(apps.get_model(label))}
        self.stdout.write(json.dumps(rows, default=str))
