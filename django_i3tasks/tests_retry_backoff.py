# django-i3tasks — Django app for managing async tasks via HTTP
# Copyright (C) 2024-2026 Ivan Bettarini
# Licensed under the GNU General Public License v3.0 or later.
# See LICENSE in the project root for full text.

from unittest.mock import patch

from django.test import TestCase, override_settings

from .types import I3TasksSettings, Queue
from .utils import TaskObj


def _failing_task(*args, **kwargs):
    raise ValueError("intentional test failure")


def _i3tasks_settings(**overrides):
    defaults = dict(
        namespace='test',
        default_queue=Queue('default', 'default', 'http://host/push/'),
        other_queues=(),
        schedules=(),
    )
    defaults.update(overrides)
    return I3TasksSettings(**defaults)


class RetryBackoffSecondsTest(TestCase):

    def test_disabled_when_base_is_none(self):
        with override_settings(I3TASKS=_i3tasks_settings(task_retry_backoff_base_seconds=None)):
            self.assertEqual(TaskObj._retry_backoff_seconds(1), 0)

    def test_disabled_when_base_is_zero(self):
        with override_settings(I3TASKS=_i3tasks_settings(task_retry_backoff_base_seconds=0)):
            self.assertEqual(TaskObj._retry_backoff_seconds(1), 0)

    def test_exponential_growth(self):
        with override_settings(I3TASKS=_i3tasks_settings(
            task_retry_backoff_base_seconds=2, task_retry_backoff_max_seconds=60,
        )):
            self.assertEqual(TaskObj._retry_backoff_seconds(1), 2)  # 2 * 2^0
            self.assertEqual(TaskObj._retry_backoff_seconds(2), 4)  # 2 * 2^1
            self.assertEqual(TaskObj._retry_backoff_seconds(3), 8)  # 2 * 2^2

    def test_capped_at_max(self):
        with override_settings(I3TASKS=_i3tasks_settings(
            task_retry_backoff_base_seconds=2, task_retry_backoff_max_seconds=5,
        )):
            self.assertEqual(TaskObj._retry_backoff_seconds(5), 5)  # 2*2^4=32, capped to 5


class RunFromAsyncBackoffTest(TestCase):

    def _build_failing_try(self):
        task_obj = TaskObj(
            func=_failing_task,
            task_args=[],
            task_kwargs={},
            max_retries=3,
            pubsub_system_utils=object(),
            pubsub_task_utils=object(),
        )
        try_obj = task_obj.get_try_obj(try_number=1)
        return task_obj, try_obj.task_execution_try_db_instance

    def test_sleeps_before_reenqueue_when_backoff_enabled(self):
        with override_settings(I3TASKS=_i3tasks_settings(
            task_retry_backoff_base_seconds=2, task_retry_backoff_max_seconds=60,
        )):
            task_obj, task_execution_try = self._build_failing_try()
            with patch('django_i3tasks.utils.time.sleep') as mock_sleep, \
                 patch.object(TaskObj, 'enqueue') as mock_enqueue:
                task_obj.run_from_async(task_execution_try_db_instance=task_execution_try)

            mock_sleep.assert_called_once_with(2)
            mock_enqueue.assert_called_once()

    def test_no_sleep_when_backoff_disabled(self):
        with override_settings(I3TASKS=_i3tasks_settings(task_retry_backoff_base_seconds=None)):
            task_obj, task_execution_try = self._build_failing_try()
            with patch('django_i3tasks.utils.time.sleep') as mock_sleep, \
                 patch.object(TaskObj, 'enqueue') as mock_enqueue:
                task_obj.run_from_async(task_execution_try_db_instance=task_execution_try)

            mock_sleep.assert_not_called()
            mock_enqueue.assert_called_once()
