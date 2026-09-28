"""Prints the highest local Suggestion primary key (0 if none), used by
ops/sync_production.sh pull-suggestions as the --since-id for dump_new_suggestions."""
from django.core.management.base import BaseCommand

from directory.models import Suggestion


class Command(BaseCommand):
    help = "Print the highest local Suggestion pk (0 if none)."

    def handle(self, *args, **options):
        max_id = Suggestion.objects.order_by('-pk').values_list('pk', flat=True).first() or 0
        return str(max_id)
