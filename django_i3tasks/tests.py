from django.test import TestCase
from .models import TaskGroup
from .chain import ChainHandle
from .models import TaskExecution, TaskExecutionTry
from .tests_tasks import results


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


class ChainHandleTest(TestCase):

    def setUp(self):
        from .tests_tasks import task_a, task_b, task_c
        self.task_a = task_a
        self.task_b = task_b
        self.task_c = task_c

    def _make_execution(self):
        """Helper: crea un TaskExecution e TaskExecutionTry minimali."""
        te = TaskExecution.objects.create(
            task_name='task_a',
            task_path='django_i3tasks.tests_tasks',
            task_args=[],
            task_kwargs={},
        )
        tt = TaskExecutionTry.objects.create(
            task_execution=te,
            try_number=1,
        )
        return te, tt

    def test_chain_handle_then_appends_step(self):
        te, tt = self._make_execution()
        handle = ChainHandle(task_execution_try=tt, steps=[])
        handle.then(self.task_b, 'arg1', kwarg1='v1')
        self.assertEqual(len(handle.steps), 1)
        step = handle.steps[0]
        self.assertEqual(step['func_name'], 'task_b')
        self.assertEqual(step['module_name'], 'django_i3tasks.tests_tasks')
        self.assertEqual(step['args'], ['arg1'])
        self.assertEqual(step['kwargs'], {'kwarg1': 'v1'})

    def test_chain_handle_then_writes_to_db(self):
        te, tt = self._make_execution()
        handle = ChainHandle(task_execution_try=tt, steps=[])
        handle.then(self.task_b)
        te.refresh_from_db()
        self.assertEqual(len(te.chain), 1)
        self.assertEqual(te.chain[0]['func_name'], 'task_b')

    def test_chain_handle_then_returns_self(self):
        te, tt = self._make_execution()
        handle = ChainHandle(task_execution_try=tt, steps=[])
        result = handle.then(self.task_b)
        self.assertIs(result, handle)

    def test_chain_handle_fluent_chaining(self):
        te, tt = self._make_execution()
        handle = ChainHandle(task_execution_try=tt, steps=[])
        handle.then(self.task_b).then(self.task_c)
        self.assertEqual(len(handle.steps), 2)
        te.refresh_from_db()
        self.assertEqual(len(te.chain), 2)

    def test_chain_handle_append_raw_step(self):
        te, tt = self._make_execution()
        handle = ChainHandle(task_execution_try=tt, steps=[])
        handle._append_raw_step({'module_name': 'mod', 'func_name': 'fn', 'args': [], 'kwargs': {}})
        self.assertEqual(len(handle.steps), 1)
        # _append_raw_step does NOT write to DB
        te.refresh_from_db()
        self.assertIsNone(te.chain)

    def test_build_chain_no_dispatch(self):
        handle = ChainHandle(task_execution_try=None, steps=[])
        handle.then(self.task_b)
        # steps accumulated in memory, no DB write (no task_execution_try)
        self.assertEqual(len(handle.steps), 1)


class TaskDecoratorDelayReturnsChainHandleTest(TestCase):

    def setUp(self):
        from .tests_tasks import task_a, task_b
        self.task_a = task_a
        self.task_b = task_b

    def test_delay_returns_chain_handle(self):
        handle = self.task_a.delay()
        self.assertIsInstance(handle, ChainHandle)

    def test_delay_chain_handle_has_task_execution_try(self):
        handle = self.task_a.delay()
        self.assertIsNotNone(handle.task_execution_try)
        from .models import TaskExecutionTry
        self.assertIsInstance(handle.task_execution_try, TaskExecutionTry)

    def test_delay_then_writes_chain(self):
        handle = self.task_a.delay()
        handle.then(self.task_b)
        handle.task_execution_try.task_execution.refresh_from_db()
        self.assertEqual(len(handle.task_execution_try.task_execution.chain), 1)


class OnSuccessDecoratorTest(TestCase):

    def test_on_success_prepended_to_chain(self):
        from .tests_tasks import my_task

        handle = my_task.delay()
        handle.task_execution_try.task_execution.refresh_from_db()
        chain = handle.task_execution_try.task_execution.chain
        self.assertEqual(len(chain), 1)
        self.assertEqual(chain[0]['func_name'], 'task_b')

    def test_on_success_combined_with_then(self):
        from .tests_tasks import my_task2, task_c

        handle = my_task2.delay().then(task_c)
        handle.task_execution_try.task_execution.refresh_from_db()
        chain = handle.task_execution_try.task_execution.chain
        self.assertEqual(len(chain), 2)
        self.assertEqual(chain[0]['func_name'], 'task_b')  # on_success first
        self.assertEqual(chain[1]['func_name'], 'task_c')  # .then() after


class ChainContinuationTest(TestCase):

    def setUp(self):
        results.clear()
        from .tests_tasks import task_a, task_b, task_c, task_fail
        self.task_a = task_a
        self.task_b = task_b
        self.task_c = task_c
        self.task_fail = task_fail

    def test_chain_a_then_b_runs_in_order(self):
        self.task_a.delay().then(self.task_b)
        self.assertEqual(results, ['a', 'b'])

    def test_chain_a_then_b_then_c(self):
        self.task_a.delay().then(self.task_b).then(self.task_c)
        self.assertEqual(results, ['a', 'b', 'c'])

    def test_chain_stops_on_failure(self):
        try:
            self.task_fail.delay().then(self.task_b)
        except Exception:
            pass
        self.assertNotIn('b', results)

    def test_chain_retry_safety(self):
        self.task_a.delay().then(self.task_b)
        self.assertEqual(results.count('b'), 1)


class TaskGroupCreateTest(TestCase):

    def setUp(self):
        results.clear()
        from .tests_tasks import task_aggregator
        self.task_aggregator = task_aggregator

    def test_create_with_task_decorator(self):
        from .models import TaskGroup
        group = TaskGroup.create(
            callback=self.task_aggregator,
            total_count=3,
        )
        self.assertIsNotNone(group.pk)
        self.assertEqual(group.callback_task_name, 'task_aggregator')
        self.assertEqual(group.callback_task_path, 'django_i3tasks.tests_tasks')
        self.assertEqual(group.total_count, 3)
        self.assertEqual(group.status, TaskGroup.STATUS_PENDING)

    def test_create_with_zero_total_count_fires_callback(self):
        from .models import TaskGroup
        group = TaskGroup.create(
            callback=self.task_aggregator,
            total_count=0,
        )
        self.assertEqual(group.status, TaskGroup.STATUS_SUCCESS)
        self.assertIn('aggregator', results)

    def test_delay_with_i3group_sets_task_group(self):
        from .models import TaskGroup
        from .tests_tasks import task_a
        group = TaskGroup.create(callback=self.task_aggregator, total_count=2)
        handle = task_a.delay(__i3group__=group)
        handle.task_execution_try.task_execution.refresh_from_db()
        self.assertEqual(
            handle.task_execution_try.task_execution.task_group_id,
            group.pk,
        )

    def test_delay_without_i3group_is_standalone(self):
        from .tests_tasks import task_a
        handle = task_a.delay()
        handle.task_execution_try.task_execution.refresh_from_db()
        self.assertIsNone(handle.task_execution_try.task_execution.task_group)
