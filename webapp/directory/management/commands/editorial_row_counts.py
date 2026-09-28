"""Prints a row count per editorial model (see directory/sync.py). Run locally and on
production (via ops/sync_production.sh status) to eyeball how far apart the two databases are
before pushing.
"""
from django.apps import apps
from django.core.management.base import BaseCommand

from directory.sync import EDITORIAL_MODELS


class Command(BaseCommand):
    help = "Print a row count per editorial model."

    def handle(self, *args, **options):
        for label in EDITORIAL_MODELS:
            model = apps.get_model(label)
            self.stdout.write(f'{label}: {model.objects.count()}')
