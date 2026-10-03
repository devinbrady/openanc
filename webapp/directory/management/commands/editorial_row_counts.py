"""Prints a row count and a content hash per editorial model (see directory/sync.py), one
"app.Model: <count> <hash>" line each. Run locally and on production (via
ops/sync_production.sh status) to see whether the two databases are in precise agreement:
equal counts show the same number of rows, equal hashes show every row's field values match.

The hash covers every serialized field of every row in primary-key order (many-to-many lists
sorted), so any edit to any row changes it, including edits that leave the count unchanged.
"""
import hashlib
import json

from django.apps import apps
from django.core import serializers
from django.core.management.base import BaseCommand

from directory.sync import EDITORIAL_MODELS


def content_hash(model):
    rows = serializers.serialize('python', model.objects.order_by('pk'))
    normalized = [
        {
            'pk': row['pk'],
            'fields': {k: sorted(v) if isinstance(v, list) else v for k, v in row['fields'].items()},
        }
        for row in rows
    ]
    payload = json.dumps(normalized, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


class Command(BaseCommand):
    help = "Print a row count and content hash per editorial model."

    def handle(self, *args, **options):
        for label in EDITORIAL_MODELS:
            model = apps.get_model(label)
            self.stdout.write(f'{label}: {model.objects.count()} {content_hash(model)}')
