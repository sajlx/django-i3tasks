# django-i3tasks — Django app for managing async tasks via HTTP
# Copyright (C) 2024-2026 Ivan Bettarini
# Licensed under the GNU General Public License v3.0 or later.
# See LICENSE in the project root for full text.

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone

from .maintenance import clean_old_task_executions, old_task_executions
from .models import TaskExecution, TaskExecutionTry, TaskExecutionResult
from .types import I3TasksSettings, Queue


def _make(age_days, with_children=False):
    """Create a TaskExecution whose created_at is age_days in the past."""
    te = TaskExecution.objects.create(task_name='t', task_path='m')
    if with_children:
        tt = TaskExecutionTry.objects.create(task_execution=te, try_number=1)
        TaskExecutionResult.objects.create(task_execution_try=tt, result={'x': 1})
    # created_at is auto_now_add → override via UPDATE (bypasses auto_now_add).
    TaskExecution.objects.filter(pk=te.pk).update(
        created_at=timezone.now() - timedelta(days=age_days)
    )
    return te


def _settings_with_autoclean(delta):
    return I3TasksSettings(
        namespace='test',
        default_queue=Queue('default', 'default', 'http://localhost/i3/tasks-push/'),
        other_queues=(),
        schedules=(),
        force_sync=True,
        autoclean_older_than=delta,
    )


class CleanOldTaskExecutionsTest(TestCase):

    def test_deletes_only_rows_older_than_threshold(self):
        old = _make(age_days=40)
        recent = _make(age_days=5)
        deleted = clean_old_task_executions(older_than=timedelta(days=30))
        self.assertEqual(deleted, 1)
        self.assertFalse(TaskExecution.objects.filter(pk=old.pk).exists())
        self.assertTrue(TaskExecution.objects.filter(pk=recent.pk).exists())

    def test_cascade_removes_tries_and_results(self):
        old = _make(age_days=40, with_children=True)
        clean_old_task_executions(older_than=timedelta(days=30))
        self.assertFalse(TaskExecutionTry.objects.filter(task_execution_id=old.pk).exists())
        self.assertEqual(TaskExecutionResult.objects.count(), 0)

    def test_no_threshold_is_noop(self):
        _make(age_days=40)
        # No explicit older_than and (default test_settings) no autoclean configured.
        deleted = clean_old_task_executions()
        self.assertEqual(deleted, 0)
        self.assertEqual(TaskExecution.objects.count(), 1)

    def test_old_task_executions_returns_none_without_threshold(self):
        self.assertIsNone(old_task_executions())

    @override_settings(I3TASKS=_settings_with_autoclean(timedelta(days=30)))
    def test_threshold_from_setting(self):
        old = _make(age_days=40)
        recent = _make(age_days=5)
        deleted = clean_old_task_executions()  # picks up the setting
        self.assertEqual(deleted, 1)
        self.assertFalse(TaskExecution.objects.filter(pk=old.pk).exists())
        self.assertTrue(TaskExecution.objects.filter(pk=recent.pk).exists())

    def test_batched_delete_removes_all_matching(self):
        for _ in range(5):
            _make(age_days=40)
        _make(age_days=5)
        deleted = clean_old_task_executions(older_than=timedelta(days=30), batch_size=2)
        self.assertEqual(deleted, 5)
        # only the recent row survives
        self.assertEqual(TaskExecution.objects.count(), 1)


class CreatedAtIndexTest(TestCase):

    def test_created_at_index_present(self):
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(
                cursor, TaskExecution._meta.db_table
            )
        indexed_columns = [c['columns'] for c in constraints.values() if c.get('index')]
        self.assertIn(['created_at'], indexed_columns)


class I3TasksCleanCommandTest(TestCase):

    def test_command_deletes_with_days(self):
        _make(age_days=40)
        _make(age_days=5)
        out = StringIO()
        call_command('i3tasks_clean', '--days', '30', stdout=out)
        self.assertIn('Deleted 1', out.getvalue())
        self.assertEqual(TaskExecution.objects.count(), 1)

    def test_command_dry_run_deletes_nothing(self):
        _make(age_days=40)
        out = StringIO()
        call_command('i3tasks_clean', '--days', '30', '--dry-run', stdout=out)
        self.assertIn('[dry-run] 1', out.getvalue())
        self.assertEqual(TaskExecution.objects.count(), 1)

    def test_command_errors_without_window(self):
        # No --days and no configured threshold → error.
        with self.assertRaises(CommandError):
            call_command('i3tasks_clean')


class AutocleanTaskTest(TestCase):
    """The built-in autoclean_task runs the cleanup through i3tasks itself."""

    def test_task_deletes_old_rows(self):
        from .tasks import autoclean_task
        old = _make(age_days=40)
        recent = _make(age_days=5)
        # force_sync=True in test settings → runs synchronously on delay().
        autoclean_task.delay(days=30)
        self.assertFalse(TaskExecution.objects.filter(pk=old.pk).exists())
        self.assertTrue(TaskExecution.objects.filter(pk=recent.pk).exists())

    def test_task_noop_without_window(self):
        from .tasks import autoclean_task
        old = _make(age_days=40)
        autoclean_task.delay()  # no days, no configured threshold → no-op
        self.assertTrue(TaskExecution.objects.filter(pk=old.pk).exists())
