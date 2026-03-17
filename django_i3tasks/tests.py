from django.test import TestCase
from .models import TaskGroup


class TaskGroupModelTest(TestCase):

    def test_create_task_group_basic(self):
        group = TaskGroup.objects.create(
            callback_task_name='task_aggregator',
            callback_task_path='django_i3tasks.tests_tasks',
            callback_task_args=[],
            callback_task_kwargs={},
            total_count=3,
        )
        self.assertEqual(group.status, TaskGroup.STATUS_PENDING)
        self.assertEqual(group.completed_count, 0)
        self.assertEqual(group.failed_count, 0)
        self.assertEqual(group.total_count, 3)
        self.assertIsNone(group.callback_chain)

    def test_task_group_status_constants(self):
        self.assertEqual(TaskGroup.STATUS_PENDING, 'pending')
        self.assertEqual(TaskGroup.STATUS_SUCCESS, 'success')
        self.assertEqual(TaskGroup.STATUS_FAILED, 'failed')
