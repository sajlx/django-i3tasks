# django-i3tasks — Django app for managing async tasks via HTTP
# Copyright (C) 2024-2026 Ivan Bettarini
# Licensed under the GNU General Public License v3.0 or later.
# See LICENSE in the project root for full text.

import datetime
from unittest import mock

from django.conf import settings
from django.test import RequestFactory, TestCase, override_settings

from . import tests_tasks, views
from .types import I3TasksSettings, Schedule


def _settings_with(*schedules):
    base = settings.I3TASKS
    return I3TasksSettings(
        namespace=base.namespace,
        default_queue=base.default_queue,
        other_queues=(),
        schedules=schedules,
        force_sync=True,
        run_queue_create_command_on_startup=False,
        task_retry_backoff_base_seconds=None,
    )


def _beat_at(utc_moment):
    """POST the beat with the clock frozen at `utc_moment`."""
    clock = mock.Mock(wraps=datetime)
    clock.timezone = datetime.timezone
    clock.datetime = mock.Mock(wraps=datetime.datetime)
    clock.datetime.now.return_value = utc_moment
    with mock.patch.object(views, "datetime", clock):
        return views.BeatTaskView.as_view()(RequestFactory().post("/i3/tasks-beat/"))


class BeatTimezoneTest(TestCase):

    def setUp(self):
        tests_tasks.results.clear()

    def _runs(self, schedule, utc_moment):
        with override_settings(I3TASKS=_settings_with(schedule)):
            response = _beat_at(utc_moment)
        self.assertEqual(response.status_code, 200)
        return tests_tasks.results == ["a"]

    def test_schedule_with_a_timezone_matches_the_local_wall_clock(self):
        nine_rome = Schedule("django_i3tasks.tests_tasks", "task_a", "0 9 * * *", [], {}, "Europe/Rome")
        cases = [
            (datetime.datetime(2026, 1, 15, 8, 0, 20, tzinfo=datetime.timezone.utc), True),   # CET, UTC+1
            (datetime.datetime(2026, 7, 15, 7, 0, 20, tzinfo=datetime.timezone.utc), True),   # CEST, UTC+2
            (datetime.datetime(2026, 1, 15, 9, 0, 20, tzinfo=datetime.timezone.utc), False),  # 10:00 in Rome
        ]
        for moment, expected in cases:
            with self.subTest(moment=moment):
                tests_tasks.results.clear()
                self.assertEqual(self._runs(nine_rome, moment), expected)

    def test_schedule_without_a_timezone_reads_the_cron_in_utc(self):
        nine_utc = Schedule("django_i3tasks.tests_tasks", "task_a", "0 9 * * *", [], {})
        self.assertIsNone(nine_utc.timezone)
        self.assertTrue(self._runs(nine_utc, datetime.datetime(2026, 1, 15, 9, 0, 5, tzinfo=datetime.timezone.utc)))
