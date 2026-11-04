# django-i3tasks — Django app for managing async tasks via HTTP
# Copyright (C) 2024-2026 Ivan Bettarini
# Licensed under the GNU General Public License v3.0 or later.
# See LICENSE in the project root for full text.

import threading
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings

from . import memory
from .types import I3TasksSettings, Queue
from .utils import TaskObj


def _i3tasks_settings(**overrides):
    defaults = dict(
        namespace='test',
        default_queue=Queue('default', 'default', 'http://host/push/'),
        other_queues=(),
        schedules=(),
        force_sync=True,
        task_retry_backoff_base_seconds=None,
    )
    defaults.update(overrides)
    return I3TasksSettings(**defaults)


class ReadRssTest(SimpleTestCase):

    def test_reads_a_positive_number_on_linux(self):
        rss = memory.read_rss_mb()
        self.assertIsNotNone(rss)
        self.assertGreater(rss, 1)

    def test_returns_none_when_proc_is_missing(self):
        with patch('builtins.open', side_effect=FileNotFoundError):
            self.assertIsNone(memory.read_rss_mb())


class TrackMemoryTest(SimpleTestCase):

    def _line(self, logs):
        [line] = [m for m in logs.output if 'i3tasks_memory' in m]
        return line

    def test_logs_one_line_with_status_ok(self):
        with self.assertLogs('django_i3tasks.memory', level='INFO') as logs:
            with memory.track_memory('mytask', execution_id=7, interval_ms=10):
                pass
        line = self._line(logs)
        self.assertIn('func=mytask', line)
        self.assertIn('id=7', line)
        self.assertIn('status=ok', line)
        self.assertIn('in_flight_max=1', line)
        self.assertIn('in_flight=-', line)

    def test_peak_is_above_end_after_a_temporary_allocation(self):
        with self.assertLogs('django_i3tasks.memory', level='INFO') as logs:
            with memory.track_memory('alloc', interval_ms=10):
                block = bytearray(80 * 1024 * 1024)
                block[::4096] = b'x' * len(block[::4096])  # tocca le pagine: entrano nell'RSS
                import time
                time.sleep(0.1)
                del block
        line = self._line(logs)
        fields = dict(part.split('=', 1) for part in line.split() if '=' in part)
        self.assertGreater(float(fields['peak_mb']) - float(fields['start_mb']), 50)

    def test_failure_is_logged_and_not_swallowed(self):
        with self.assertLogs('django_i3tasks.memory', level='INFO') as logs:
            with self.assertRaises(ValueError):
                with memory.track_memory('boom', interval_ms=10):
                    raise ValueError('x')
        self.assertIn('status=error', self._line(logs))

    def test_lists_tasks_running_at_the_same_time(self):
        inside = threading.Event()
        release = threading.Event()

        def other():
            with memory.track_memory('other_task', interval_ms=10):
                inside.set()
                release.wait(2)

        thread = threading.Thread(target=other)
        thread.start()
        inside.wait(2)
        with self.assertLogs('django_i3tasks.memory', level='INFO') as logs:
            with memory.track_memory('main_task', interval_ms=10):
                pass
        release.set()
        thread.join()
        line = self._line(logs)
        self.assertIn('in_flight_max=2', line)
        self.assertIn('in_flight=other_task', line)
        self.assertEqual(memory._running, {})

    def test_registry_is_cleaned_even_on_error(self):
        with self.assertRaises(RuntimeError):
            with memory.track_memory('x', interval_ms=10):
                raise RuntimeError
        self.assertEqual(memory._running, {})


def _noop(*args, **kwargs):
    return 'done'


class RunIntegrationTest(TestCase):

    def _run(self):
        task = TaskObj.__new__(TaskObj)
        task.func = _noop
        task.func_name = '_noop'
        task.module_name = __name__
        task.bind = False
        task.task_execution_db_instance = type('E', (), {'id': 99})()
        return TaskObj._run(task)

    def test_off_by_default(self):
        with override_settings(I3TASKS=_i3tasks_settings()):
            with patch('django_i3tasks.utils.track_memory') as tracker:
                self.assertEqual(self._run(), 'done')
        tracker.assert_not_called()

    def test_enabled_logs_memory_for_the_run(self):
        with override_settings(I3TASKS=_i3tasks_settings(memory_log=True, memory_log_interval_ms=10)):
            with self.assertLogs('django_i3tasks.memory', level='INFO') as logs:
                self.assertEqual(self._run(), 'done')
        self.assertTrue(any('func=_noop' in m and 'id=99' in m for m in logs.output))
