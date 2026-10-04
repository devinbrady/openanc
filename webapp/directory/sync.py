"""Shared definitions for the local <-> production data sync tooling (see ops/sync_production.sh
and the dump_editorial_data / load_editorial_data / dump_new_suggestions /
dump_reviewed_suggestions management commands).

The model behind this: from here on, Person/CommissionerTerm/Candidate/etc rows are only ever
created in the LOCAL admin/database. Production's only organic write path is the public
Suggestion form. That's what makes plain primary-key-based loaddata upserts safe in both
directions, with no merge/conflict logic needed.

EDITORIAL_MODELS is every model that can change locally and needs to reach production, in an
order that's always safe to load (each model's foreign keys point only at models earlier in the
list) -- this mirrors the proven insertion order already used by
management/commands/import_legacy_data.py. Suggestion is deliberately excluded here: it has its
own pull-down/push-back flow (dump_new_suggestions / dump_reviewed_suggestions) since it's the
one model production writes to on its own. Historical* shadow tables (django-simple-history) are
also excluded on purpose -- history is local-only; the Updates-page draft generator reads local
history and writes an ordinary SiteUpdate row, which *is* synced normally.
"""

EDITORIAL_MODELS = [
    'directory.MapColor',
    'directory.Ward',
    'directory.ANC',
    'directory.ANCOverlap',
    'directory.District',
    'directory.DistrictOverlap',
    'directory.Person',
    'directory.CommissionerTerm',
    'directory.Election',
    'directory.CandidateStatus',
    'directory.Candidate',
    'directory.ElectionResult',
    'directory.WriteInWinner',
    'directory.SiteUpdate',
]

# What `ops/sync_production.sh status` compares: the editorial models plus Suggestion. Suggestion
# isn't pushed with the editorial fixture (it has its own pull/push-back flow), but it should still
# agree between the two databases once you've pulled new submissions and pushed reviews back.
STATUS_MODELS = EDITORIAL_MODELS + ['directory.Suggestion']


def normalized_rows(model):
    """Every row of `model` as [{'pk': ..., 'fields': {...}}] in pk order, many-to-many lists
    sorted so ordering noise can't make two identical databases look different. Used for the
    content hashes and row-level diffs behind `sync_production.sh status`.

    Datetimes are truncated to milliseconds: the push goes through dumpdata's JSON, and Django's
    JSON encoder drops microseconds, so production always holds millisecond values. Comparing at
    full precision would flag every pushed row as different forever.
    """
    import datetime

    from django.core import serializers

    def normalize(value):
        if isinstance(value, list):
            return sorted(value)
        if isinstance(value, datetime.datetime):
            return value.replace(microsecond=value.microsecond // 1000 * 1000)
        return value

    return [
        {
            'pk': row['pk'],
            'fields': {k: normalize(v) for k, v in row['fields'].items()},
        }
        for row in serializers.serialize('python', model.objects.order_by('pk'))
    ]
