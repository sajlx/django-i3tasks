# django-i3tasks — Django app for managing async tasks via HTTP
# Copyright (C) 2024-2026 Ivan Bettarini
# Licensed under the GNU General Public License v3.0 or later.
# See LICENSE in the project root for full text.

import json
import uuid as uuid_module

from django.test import TestCase, RequestFactory

from .models import TaskExecution, TaskExecutionTry, TaskExecutionResult
from .views import TaskStatusView


class TaskExecutionUuidTest(TestCase):

    def test_uuid_auto_assigned(self):
        te = TaskExecution.objects.create(
            task_name='t', task_path='m', task_args=[], task_kwargs={},
        )
        self.assertIsInstance(te.uuid, uuid_module.UUID)

    def test_uuid_is_unique_per_row(self):
        te1 = TaskExecution.objects.create(task_name='t', task_path='m')
        te2 = TaskExecution.objects.create(task_name='t', task_path='m')
        self.assertNotEqual(te1.uuid, te2.uuid)


class ChainHandleIdAccessorsTest(TestCase):

    def setUp(self):
        from .tests_tasks import task_a
        self.task_a = task_a

    def test_handle_exposes_id_and_uuid(self):
        handle = self.task_a.delay()
        te = handle.task_execution_try.task_execution
        self.assertEqual(handle.task_execution_id, te.id)
        self.assertEqual(handle.task_uuid, te.uuid)
        self.assertIs(handle.task_execution, te)

    def test_build_chain_handle_accessors_are_none(self):
        from .chain import ChainHandle
        handle = ChainHandle(task_execution_try=None)
        self.assertIsNone(handle.task_execution_id)
        self.assertIsNone(handle.task_uuid)
        self.assertIsNone(handle.task_execution)


class TaskStatusViewTest(TestCase):

    def setUp(self):
        self.factory = RequestFactory()

    def _make_task(self, success=True, completed=True, with_result=True):
        te = TaskExecution.objects.create(
            task_name='my_task', task_path='app.tasks',
            task_args=[1, 2], task_kwargs={'k': 'v'},
        )
        tt = TaskExecutionTry.objects.create(
            task_execution=te, try_number=1,
            is_completed=completed, is_success=success,
        )
        if with_result:
            TaskExecutionResult.objects.create(task_execution_try=tt, result={'ok': True})
        return te, tt

    def _get(self, **kwargs):
        request = self.factory.get('/i3/tasks-status/x/')
        response = TaskStatusView.as_view()(request, **kwargs)
        return response, json.loads(response.content)

    def test_lookup_by_id(self):
        te, _ = self._make_task()
        response, body = self._get(task_id=te.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body['task']['id'], te.id)
        self.assertEqual(body['task']['uuid'], str(te.uuid))
        self.assertEqual(body['status'], 'success')
        self.assertEqual(len(body['tries']), 1)
        self.assertEqual(body['tries'][0]['result'], {'ok': True})

    def test_lookup_by_uuid(self):
        te, _ = self._make_task()
        response, body = self._get(task_uuid=te.uuid)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body['task']['id'], te.id)
        self.assertEqual(body['task']['uuid'], str(te.uuid))

    def test_not_found_by_id(self):
        response, body = self._get(task_id=999999)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(body['status'], 'not_found')

    def test_not_found_by_uuid(self):
        response, body = self._get(task_uuid=uuid_module.uuid4())
        self.assertEqual(response.status_code, 404)

    def test_status_failed(self):
        te, _ = self._make_task(success=False, completed=True, with_result=False)
        _, body = self._get(task_id=te.id)
        self.assertEqual(body['status'], 'failed')

    def test_status_pending(self):
        te = TaskExecution.objects.create(task_name='t', task_path='m')
        TaskExecutionTry.objects.create(task_execution=te, try_number=1)
        _, body = self._get(task_id=te.id)
        self.assertEqual(body['status'], 'pending')

    def test_status_unknown_no_tries(self):
        te = TaskExecution.objects.create(task_name='t', task_path='m')
        _, body = self._get(task_id=te.id)
        self.assertEqual(body['status'], 'unknown')
        self.assertEqual(body['tries'], [])
