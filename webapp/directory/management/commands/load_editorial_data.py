"""Run ON PRODUCTION (invoked remotely by ops/sync_production.sh -- never run this against your
own local database with a fixture from somewhere else). Loads a JSON fixture produced by
dump_editorial_data. Safe under the standing rule that editorial rows are only ever created
locally: loaddata upserts by primary key, so this only ever inserts new rows or updates existing
ones to match local -- it never deletes on its own.

--prune-manifest catches the other half of that: rows that were deleted locally (and so are
missing from the fixture, but would otherwise linger on production forever since loaddata never
deletes). Defaults to a dry run that only prints what *would* be removed; pass --yes to actually
delete.

Usage:
  python manage.py load_editorial_data editorial.json
  python manage.py load_editorial_data editorial.json --prune-manifest manifest.json
  python manage.py load_editorial_data editorial.json --prune-manifest manifest.json --yes
"""
import json

from django.apps import apps
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Load an editorial data fixture produced by dump_editorial_data. Run on production."

    def add_arguments(self, parser):
        parser.add_argument('fixture_path')
        parser.add_argument('--prune-manifest', help='Path to a PK manifest from dump_editorial_data.')
        parser.add_argument(
            '--yes', action='store_true',
            help='Actually delete rows absent from the manifest (default: dry run, only prints counts).',
        )

    def handle(self, *args, **options):
        with transaction.atomic():
            call_command('loaddata', options['fixture_path'])
        self.stdout.write(self.style.SUCCESS(f"Loaded {options['fixture_path']}"))

        if not options['prune_manifest']:
            return

        with open(options['prune_manifest']) as f:
            manifest = json.load(f)

        for label, pks in manifest.items():
            model = apps.get_model(label)
            to_delete = model.objects.exclude(pk__in=pks)
            count = to_delete.count()
            if count == 0:
                continue
            if options['yes']:
                to_delete.delete()
                self.stdout.write(self.style.WARNING(f'{label}: deleted {count} row(s) not present locally'))
            else:
                self.stdout.write(self.style.WARNING(
                    f'{label}: would delete {count} row(s) not present locally (dry run -- pass --yes to actually delete)'
                ))
