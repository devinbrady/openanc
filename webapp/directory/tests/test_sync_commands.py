"""Tests for the local <-> production sync commands that ops/sync_production.sh shells out to."""
import io
import json
import os
import tempfile

from django.core import serializers
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from directory.models import Person, Suggestion
from directory.sync import EDITORIAL_MODELS
from directory.tests.factories import make_district, make_person


class TempDirMixin:
    def setUp(self):
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def path(self, name):
        return os.path.join(self._tmp.name, name)


def run(command, *args, **kwargs):
    out = io.StringIO()
    result = call_command(command, *args, stdout=out, **kwargs)
    return result, out.getvalue()


class DumpEditorialDataTests(TempDirMixin, TestCase):
    def test_writes_fixture_and_manifest_of_every_editorial_model(self):
        district = make_district(designator='1A01')
        person = make_person(full_name='Jane Doe')
        Suggestion.objects.create(message='not editorial')

        _, out = run('dump_editorial_data', output=self.path('data.json'), manifest=self.path('manifest.json'))

        with open(self.path('data.json')) as f:
            data = json.load(f)
        models_dumped = {row['model'] for row in data}
        self.assertIn('directory.person', models_dumped)
        self.assertIn('directory.district', models_dumped)
        self.assertNotIn('directory.suggestion', models_dumped)

        with open(self.path('manifest.json')) as f:
            manifest = json.load(f)
        self.assertEqual(list(manifest), EDITORIAL_MODELS)
        self.assertEqual(manifest['directory.Person'], [person.pk])
        self.assertEqual(manifest['directory.District'], [district.pk])
        self.assertIn('Wrote data fixture', out)
        self.assertIn('Wrote PK manifest', out)


class LoadEditorialDataTests(TempDirMixin, TestCase):
    def dump(self):
        call_command('dump_editorial_data', output=self.path('data.json'), manifest=self.path('manifest.json'),
                     stdout=io.StringIO())

    def test_round_trip_restores_edited_rows(self):
        person = make_person(full_name='Original Name')
        self.dump()
        Person.objects.filter(pk=person.pk).update(full_name='Changed On Production')

        _, out = run('load_editorial_data', self.path('data.json'))

        person.refresh_from_db()
        self.assertEqual(person.full_name, 'Original Name')
        self.assertIn('Loaded', out)

    def test_without_manifest_extra_rows_are_left_alone(self):
        make_person(full_name='Kept')
        self.dump()
        extra = make_person(full_name='Only On Production')

        run('load_editorial_data', self.path('data.json'))

        self.assertTrue(Person.objects.filter(pk=extra.pk).exists())

    def test_prune_manifest_is_a_dry_run_by_default(self):
        make_person(full_name='Kept')
        self.dump()
        extra = make_person(full_name='Deleted Locally')

        _, out = run('load_editorial_data', self.path('data.json'), prune_manifest=self.path('manifest.json'))

        self.assertTrue(Person.objects.filter(pk=extra.pk).exists())
        self.assertIn('directory.Person: would delete 1 row(s)', out)

    def test_prune_manifest_with_yes_deletes_rows_absent_locally(self):
        kept = make_person(full_name='Kept')
        self.dump()
        extra = make_person(full_name='Deleted Locally')

        _, out = run('load_editorial_data', self.path('data.json'), prune_manifest=self.path('manifest.json'), yes=True)

        self.assertFalse(Person.objects.filter(pk=extra.pk).exists())
        self.assertTrue(Person.objects.filter(pk=kept.pk).exists())
        self.assertIn('directory.Person: deleted 1 row(s)', out)

    def test_prune_with_nothing_extra_prints_nothing_about_deletes(self):
        make_person(full_name='Kept')
        self.dump()

        _, out = run('load_editorial_data', self.path('data.json'), prune_manifest=self.path('manifest.json'), yes=True)

        self.assertNotIn('delete', out)


class SuggestionSyncCommandTests(TempDirMixin, TestCase):
    def test_max_suggestion_id_is_zero_with_no_suggestions(self):
        result, _ = run('max_suggestion_id')
        self.assertEqual(result, '0')

    def test_max_suggestion_id_is_highest_pk(self):
        Suggestion.objects.create(message='a')
        latest = Suggestion.objects.create(message='b')
        result, _ = run('max_suggestion_id')
        self.assertEqual(result, str(latest.pk))

    def test_dump_new_suggestions_returns_only_rows_after_since_id(self):
        older = Suggestion.objects.create(message='already pulled')
        newer = Suggestion.objects.create(message='new on production')

        result, _ = run('dump_new_suggestions', since_id=older.pk)

        rows = json.loads(result)
        self.assertEqual([row['pk'] for row in rows], [newer.pk])
        self.assertEqual(rows[0]['fields']['message'], 'new on production')

    def test_dump_new_suggestions_defaults_to_everything(self):
        Suggestion.objects.create(message='a')
        Suggestion.objects.create(message='b')
        result, _ = run('dump_new_suggestions')
        self.assertEqual(len(json.loads(result)), 2)

    def test_dump_reviewed_suggestions_excludes_pending(self):
        Suggestion.objects.create(message='pending')
        approved = Suggestion.objects.create(message='approved', status=Suggestion.STATUS_APPROVED)
        rejected = Suggestion.objects.create(message='rejected', status=Suggestion.STATUS_REJECTED)

        _, out = run('dump_reviewed_suggestions', output=self.path('reviewed.json'))

        with open(self.path('reviewed.json')) as f:
            pks = [obj.object.pk for obj in serializers.deserialize('json', f.read())]
        self.assertEqual(pks, [approved.pk, rejected.pk])
        self.assertIn('Wrote 2 reviewed suggestion(s)', out)


class EditorialRowsTests(TestCase):
    def test_prints_rows_keyed_by_pk(self):
        person = make_person(full_name='Jane Doe')
        _, out = run('editorial_rows', 'directory.Person')
        rows = json.loads(out)
        self.assertEqual(rows[str(person.pk)]['full_name'], 'Jane Doe')

    def test_includes_suggestion_since_status_compares_it(self):
        suggestion = Suggestion.objects.create(message='hello')
        _, out = run('editorial_rows', 'directory.Suggestion')
        self.assertEqual(json.loads(out)[str(suggestion.pk)]['message'], 'hello')

    def test_rejects_models_that_are_not_synced(self):
        with self.assertRaisesMessage(CommandError, 'is not a synced model'):
            run('editorial_rows', 'directory.PersonImportBatch')
