# Pull Worker System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `PushQueue`/`PullQueue` types and a `i3tasks_worker` management command that pulls from a Pub/Sub pull subscription and executes tasks using the existing retry infrastructure.

**Architecture:** `PushQueue` and `PullQueue` namedtuples replace the single `Queue` type (with `Queue = PushQueue` alias for backward compat). `PubSubSystemUtils` gains `pull_messages()` and `acknowledge()` methods. `i3tasks_worker` loops, pulling messages and delegating execution to `TaskObj.run_from_async()` which already handles retries internally.

**Tech Stack:** Python namedtuples, Google Cloud Pub/Sub SDK (`google-cloud-pubsub`), Django management commands, `unittest.mock` for tests.

**Spec:** `docs/superpowers/specs/2026-03-23-pull-worker-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `django_i3tasks/types.py` | Modify | Add `PushQueue`, `PullQueue`; alias `Queue = PushQueue` |
| `django_i3tasks/queue_manager/google_pubsub.py` | Modify | Update `create_subscription()` for PullQueue; add `pull_messages()`, `acknowledge()` |
| `django_i3tasks/management/commands/i3tasks_ensure_pubsub.py` | Modify | Fix `other_queues` loop — use `isinstance` instead of `.push_endpoint` access |
| `django_i3tasks/management/commands/i3tasks_worker.py` | Create | Management command with pull loop |
| `django_i3tasks/tests_pull_worker.py` | Create | All tests for this feature |
| `README.md` | Modify | Document pull queues and `i3tasks_worker` command |

---

## Task 1: Add `PushQueue` and `PullQueue` types

**Files:**
- Modify: `django_i3tasks/types.py`
- Test: `django_i3tasks/tests_pull_worker.py`

- [ ] **Step 1: Create the test file with type tests**

```python
# django_i3tasks/tests_pull_worker.py
from django.test import TestCase
from django_i3tasks.types import PushQueue, PullQueue, Queue


class PushQueuePullQueueTypesTest(TestCase):

    def test_queue_alias_is_pushqueue(self):
        self.assertIs(Queue, PushQueue)

    def test_pushqueue_fields(self):
        q = PushQueue(queue_name='default', subscription_name='sub', push_endpoint='http://host/push/')
        self.assertEqual(q.queue_name, 'default')
        self.assertEqual(q.subscription_name, 'sub')
        self.assertEqual(q.push_endpoint, 'http://host/push/')

    def test_pullqueue_fields(self):
        q = PullQueue(queue_name='heavy', subscription_name='heavy-pull')
        self.assertEqual(q.queue_name, 'heavy')
        self.assertEqual(q.subscription_name, 'heavy-pull')

    def test_pullqueue_has_no_push_endpoint(self):
        q = PullQueue(queue_name='heavy', subscription_name='heavy-pull')
        self.assertFalse(hasattr(q, 'push_endpoint'))

    def test_isinstance_discrimination(self):
        push = PushQueue('default', 'sub', 'http://host/')
        pull = PullQueue('heavy', 'heavy-pull')
        self.assertIsInstance(push, PushQueue)
        self.assertNotIsInstance(pull, PushQueue)
        self.assertIsInstance(pull, PullQueue)
        self.assertNotIsInstance(push, PullQueue)

    def test_queue_alias_isinstance(self):
        q = Queue('default', 'sub', 'http://host/')
        self.assertIsInstance(q, PushQueue)
        self.assertNotIsInstance(q, PullQueue)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test django_i3tasks.tests_pull_worker.PushQueuePullQueueTypesTest -v 2
```

Expected: ImportError or AttributeError — `PushQueue` and `PullQueue` don't exist yet.

- [ ] **Step 3: Update `types.py`**

Replace the existing `Queue = namedtuple(...)` with:

```python
from collections import namedtuple

PushQueue = namedtuple('PushQueue', [
    'queue_name',
    'subscription_name',
    'push_endpoint',
])

PullQueue = namedtuple('PullQueue', [
    'queue_name',
    'subscription_name',
])

Queue = PushQueue  # backward-compatible alias

Schedule = namedtuple('Schedule', [
    'module_name',
    'func_name',
    'cron',
    'args',
    'kwargs',
])
```

Keep `I3TasksSettings` class unchanged below.

- [ ] **Step 4: Run tests to verify they pass**

```bash
python manage.py test django_i3tasks.tests_pull_worker.PushQueuePullQueueTypesTest -v 2
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
python manage.py test django_i3tasks -v 2
```

Expected: All existing tests PASS.

- [ ] **Step 6: Commit**

```bash
git add django_i3tasks/types.py django_i3tasks/tests_pull_worker.py
git commit -m "feat: add PushQueue and PullQueue types, alias Queue = PushQueue"
```

---

## Task 2: Update `create_subscription()` for pull queues

**Files:**
- Modify: `django_i3tasks/queue_manager/google_pubsub.py`
- Test: `django_i3tasks/tests_pull_worker.py`

Current `create_subscription()` always creates a push subscription with `push_config`. It must skip `push_config` when the queue is a `PullQueue`.

> **Note on signature:** The spec describes `create_subscription(queue)`, but this plan keeps the existing `create_subscription(self, endpoint=None)` signature and performs the push/pull lookup internally using `self.topic_name`. This avoids changing all callers and is more backward-compatible. The behaviour matches the spec exactly.

- [ ] **Step 1: Add test for pull subscription creation**

Append to `django_i3tasks/tests_pull_worker.py`:

```python
from unittest.mock import MagicMock, patch
from django_i3tasks.queue_manager.google_pubsub import PubSubSystemUtils


class CreateSubscriptionTest(TestCase):

    def _make_system_utils(self, topic_name='heavy', subscription_name='heavy-pull'):
        with patch.object(PubSubSystemUtils, '__init__', lambda self, **kw: None):
            utils = PubSubSystemUtils.__new__(PubSubSystemUtils)
        utils.project_id = 'test-project'
        utils.topic_name = topic_name
        utils.subscription_name = subscription_name
        utils.namespace = 'tasks.test'
        utils.encoding = 'utf-8'
        utils._publisher_client = None
        utils._subscription_client = None
        utils._queue_already_exists = None
        utils._subscription_already_exists = None
        return utils

    @patch('django_i3tasks.queue_manager.google_pubsub.settings')
    def test_pull_queue_subscription_has_no_push_config(self, mock_settings):
        from django_i3tasks.types import PushQueue, PullQueue
        mock_settings.PUBSUB_CONFIG = {'EMULATOR': True, 'PROJECT_ID': 'test-project'}
        mock_settings.I3TASKS.namespace = 'tasks.test'
        mock_settings.I3TASKS.default_queue = PushQueue('default', 'default', 'http://host/push/')
        mock_settings.I3TASKS.other_queues = [PullQueue('heavy', 'heavy-pull')]

        utils = self._make_system_utils(topic_name='heavy', subscription_name='heavy-pull')

        mock_subscriber = MagicMock()
        mock_publisher = MagicMock()
        mock_publisher.topic_path.return_value = 'projects/test-project/topics/tasks.test.heavy'
        mock_subscriber.subscription_path.return_value = 'projects/test-project/subscriptions/tasks.test.heavy.heavy-pull'

        utils._publisher_client = mock_publisher
        utils._subscription_client = mock_subscriber

        utils.create_subscription()

        call_kwargs = mock_subscriber.create_subscription.call_args[1]
        # Must NOT have push_config set (or push_config must have no endpoint)
        push_config = call_kwargs.get('push_config', None)
        self.assertIsNone(push_config)

    @patch('django_i3tasks.queue_manager.google_pubsub.settings')
    def test_push_queue_subscription_has_push_config(self, mock_settings):
        from django_i3tasks.types import PushQueue
        mock_settings.PUBSUB_CONFIG = {'EMULATOR': True, 'PROJECT_ID': 'test-project'}
        mock_settings.I3TASKS.namespace = 'tasks.test'
        mock_settings.I3TASKS.default_queue = PushQueue('default', 'default', 'http://host/push/')
        mock_settings.I3TASKS.other_queues = []

        utils = self._make_system_utils(topic_name='default', subscription_name='default')

        mock_subscriber = MagicMock()
        mock_publisher = MagicMock()
        mock_publisher.topic_path.return_value = 'projects/test-project/topics/tasks.test.default'
        mock_subscriber.subscription_path.return_value = 'projects/test-project/subscriptions/tasks.test.default.default'

        utils._publisher_client = mock_publisher
        utils._subscription_client = mock_subscriber

        utils.create_subscription()

        call_kwargs = mock_subscriber.create_subscription.call_args[1]
        self.assertIsNotNone(call_kwargs.get('push_config'))
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test django_i3tasks.tests_pull_worker.CreateSubscriptionTest -v 2
```

Expected: FAIL — pull subscription still gets `push_config`.

- [ ] **Step 3: Update `create_subscription()` in `google_pubsub.py`**

Add import at top of file:
```python
from django_i3tasks.types import PullQueue
```

Replace the body of `create_subscription(self, endpoint=None)` with:

```python
def create_subscription(self, endpoint=None):
    from django_i3tasks.types import PullQueue
    I3TASKS: I3TasksSettings = settings.I3TASKS
    subscriber = self.get_subscription_client()
    topic_name = self.get_topic_name()
    subscription_name = self.get_subscription_name()

    # Find the queue matching this topic_name (self.topic_name is the queue_name)
    all_queues = list(I3TASKS.other_queues) + [I3TASKS.default_queue]
    matched_queue = next(
        (q for q in all_queues if q.queue_name == self.topic_name),
        I3TASKS.default_queue,
    )

    try:
        if isinstance(matched_queue, PullQueue):
            subscriber.create_subscription(
                name=subscription_name,
                topic=topic_name,
            )
        else:
            _endpoint = endpoint or matched_queue.push_endpoint
            subscriber.create_subscription(
                name=subscription_name,
                topic=topic_name,
                push_config=pubsub_v1.types.PushConfig(push_endpoint=_endpoint),
            )
    except google.api_core.exceptions.AlreadyExists:
        logger.info(f"Subscription {subscription_name} already exists")
        self._subscription_already_exists = True
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python manage.py test django_i3tasks.tests_pull_worker.CreateSubscriptionTest -v 2
```

Expected: Both tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
python manage.py test django_i3tasks -v 2
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add django_i3tasks/queue_manager/google_pubsub.py django_i3tasks/tests_pull_worker.py
git commit -m "feat: update create_subscription() to skip push_config for PullQueue"
```

---

## Task 3: Add `pull_messages()` and `acknowledge()` to `PubSubSystemUtils`

**Files:**
- Modify: `django_i3tasks/queue_manager/google_pubsub.py`
- Test: `django_i3tasks/tests_pull_worker.py`

- [ ] **Step 1: Add tests**

Append to `django_i3tasks/tests_pull_worker.py`:

```python
class PullMessagesAcknowledgeTest(TestCase):

    def _make_system_utils(self, topic_name='heavy', subscription_name='heavy-pull'):
        with patch.object(PubSubSystemUtils, '__init__', lambda self, **kw: None):
            utils = PubSubSystemUtils.__new__(PubSubSystemUtils)
        utils.project_id = 'test-project'
        utils.topic_name = topic_name
        utils.subscription_name = subscription_name
        utils.namespace = 'tasks.test'
        utils.encoding = 'utf-8'
        utils._publisher_client = None
        utils._subscription_client = None
        utils._queue_already_exists = None
        utils._subscription_already_exists = None
        return utils

    def test_pull_messages_calls_subscriber_pull(self):
        utils = self._make_system_utils()
        mock_subscriber = MagicMock()
        mock_subscriber.subscription_path.return_value = 'projects/test-project/subscriptions/tasks.test.heavy.heavy-pull'
        mock_response = MagicMock()
        mock_response.received_messages = [MagicMock(), MagicMock()]
        mock_subscriber.pull.return_value = mock_response
        utils._subscription_client = mock_subscriber

        messages = utils.pull_messages(max_messages=2)

        mock_subscriber.pull.assert_called_once_with(
            request={
                'subscription': 'projects/test-project/subscriptions/tasks.test.heavy.heavy-pull',
                'max_messages': 2,
            }
        )
        self.assertEqual(len(messages), 2)

    def test_pull_messages_returns_empty_list_when_no_messages(self):
        utils = self._make_system_utils()
        mock_subscriber = MagicMock()
        mock_subscriber.subscription_path.return_value = 'projects/test-project/subscriptions/tasks.test.heavy.heavy-pull'
        mock_response = MagicMock()
        mock_response.received_messages = []
        mock_subscriber.pull.return_value = mock_response
        utils._subscription_client = mock_subscriber

        messages = utils.pull_messages()

        self.assertEqual(messages, [])

    def test_acknowledge_calls_subscriber_acknowledge(self):
        utils = self._make_system_utils()
        mock_subscriber = MagicMock()
        mock_subscriber.subscription_path.return_value = 'projects/test-project/subscriptions/tasks.test.heavy.heavy-pull'
        utils._subscription_client = mock_subscriber

        utils.acknowledge(['ack-id-1', 'ack-id-2'])

        mock_subscriber.acknowledge.assert_called_once_with(
            request={
                'subscription': 'projects/test-project/subscriptions/tasks.test.heavy.heavy-pull',
                'ack_ids': ['ack-id-1', 'ack-id-2'],
            }
        )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python manage.py test django_i3tasks.tests_pull_worker.PullMessagesAcknowledgeTest -v 2
```

Expected: FAIL — methods don't exist yet.

- [ ] **Step 3: Add methods to `PubSubSystemUtils` in `google_pubsub.py`**

Add after `ensure_subscription()`:

```python
def pull_messages(self, max_messages=1):
    subscriber = self.get_subscription_client()
    subscription_name = self.get_subscription_name()
    response = subscriber.pull(
        request={
            'subscription': subscription_name,
            'max_messages': max_messages,
        }
    )
    return list(response.received_messages)

def acknowledge(self, ack_ids):
    subscriber = self.get_subscription_client()
    subscription_name = self.get_subscription_name()
    subscriber.acknowledge(
        request={
            'subscription': subscription_name,
            'ack_ids': ack_ids,
        }
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python manage.py test django_i3tasks.tests_pull_worker.PullMessagesAcknowledgeTest -v 2
```

Expected: All 3 tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
python manage.py test django_i3tasks -v 2
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add django_i3tasks/queue_manager/google_pubsub.py django_i3tasks/tests_pull_worker.py
git commit -m "feat: add pull_messages() and acknowledge() to PubSubSystemUtils"
```

---

## Task 4: Fix `i3tasks_ensure_pubsub` for `PullQueue` in `other_queues`

**Files:**
- Modify: `django_i3tasks/management/commands/i3tasks_ensure_pubsub.py`
- Test: `django_i3tasks/tests_pull_worker.py`

Currently the `handle()` loop over `other_queues` accesses `.push_endpoint` unconditionally, crashing on `PullQueue`.

- [ ] **Step 1: Add test**

Append to `django_i3tasks/tests_pull_worker.py`:

```python
from django.core.management import call_command
from io import StringIO


class EnsurePubsubWithPullQueueTest(TestCase):

    @patch('django_i3tasks.management.commands.i3tasks_ensure_pubsub.PubSubSystemUtils')
    @patch('django_i3tasks.management.commands.i3tasks_ensure_pubsub.settings')
    def test_ensure_pubsub_handles_pullqueue_in_other_queues(self, mock_settings, MockPubSubSystemUtils):
        from django_i3tasks.types import PushQueue, PullQueue
        mock_settings.I3TASKS.default_queue = PushQueue('default', 'default', 'http://host/push/')
        mock_settings.I3TASKS.other_queues = [
            PullQueue('heavy', 'heavy-pull'),
        ]

        mock_utils_instance = MagicMock()
        MockPubSubSystemUtils.return_value = mock_utils_instance

        # Should not raise AttributeError
        out = StringIO()
        try:
            call_command('i3tasks_ensure_pubsub', stdout=out)
        except SystemExit:
            pass

        # PubSubSystemUtils was instantiated for the pull queue
        calls = MockPubSubSystemUtils.call_args_list
        queue_names = [c[1].get('topic_name') or (c[0][0] if c[0] else None) for c in calls]
        self.assertTrue(
            any('heavy' in str(c) for c in MockPubSubSystemUtils.call_args_list)
        )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test django_i3tasks.tests_pull_worker.EnsurePubsubWithPullQueueTest -v 2
```

Expected: FAIL with `AttributeError: 'PullQueue' object has no attribute 'push_endpoint'`.

- [ ] **Step 3: Update the `handle()` loop in `i3tasks_ensure_pubsub.py`**

Replace the `for queue in settings.I3TASKS.other_queues:` block with:

```python
for queue in settings.I3TASKS.other_queues:
    from django_i3tasks.types import PullQueue
    queue_name = queue.queue_name          # present on both PushQueue and PullQueue
    subscription_name = queue.subscription_name  # same

    try:
        pub_sub_system_utils = PubSubSystemUtils(
            topic_name=queue_name,
            subscription_name=subscription_name,
        )
        pub_sub_system_utils.ensure_queue_exists()
        pub_sub_system_utils.ensure_subscription()
        # create_subscription() resolves push vs pull internally via self.topic_name
    except Exception as exc:
        logger.error(f"Error on ensure {queue_name} queue")
        logger.exception(exc)
        raise CommandError(f"Failed to ensure queue {queue_name}") from exc
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python manage.py test django_i3tasks.tests_pull_worker.EnsurePubsubWithPullQueueTest -v 2
```

Expected: PASS.

- [ ] **Step 5: Run full test suite**

```bash
python manage.py test django_i3tasks -v 2
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add django_i3tasks/management/commands/i3tasks_ensure_pubsub.py django_i3tasks/tests_pull_worker.py
git commit -m "fix: handle PullQueue in i3tasks_ensure_pubsub other_queues loop"
```

---

## Task 5: Create `i3tasks_worker` management command

**Files:**
- Create: `django_i3tasks/management/commands/i3tasks_worker.py`
- Test: `django_i3tasks/tests_pull_worker.py`

- [ ] **Step 1: Add startup validation tests**

Append to `django_i3tasks/tests_pull_worker.py`:

```python
from django.core.management.base import CommandError
from unittest.mock import patch, MagicMock


class WorkerCommandValidationTest(TestCase):

    @patch('django_i3tasks.management.commands.i3tasks_worker.settings')
    def test_unknown_queue_raises_command_error(self, mock_settings):
        from django_i3tasks.types import PushQueue
        mock_settings.I3TASKS.default_queue = PushQueue('default', 'default', 'http://host/')
        mock_settings.I3TASKS.other_queues = []

        from django_i3tasks.management.commands.i3tasks_worker import Command
        cmd = Command()
        with self.assertRaises(CommandError):
            cmd.handle(queue='nonexistent')

    @patch('django_i3tasks.management.commands.i3tasks_worker.settings')
    def test_pushqueue_raises_command_error(self, mock_settings):
        from django_i3tasks.types import PushQueue
        mock_settings.I3TASKS.default_queue = PushQueue('default', 'default', 'http://host/')
        mock_settings.I3TASKS.other_queues = []

        from django_i3tasks.management.commands.i3tasks_worker import Command
        cmd = Command()
        with self.assertRaises(CommandError):
            cmd.handle(queue='default')  # default is a PushQueue
```

- [ ] **Step 2: Add worker loop tests**

Append to `django_i3tasks/tests_pull_worker.py`:

```python
class WorkerLoopTest(TestCase):

    def _make_message(self, payload_dict, ack_id='ack-123'):
        import json
        msg = MagicMock()
        msg.ack_id = ack_id
        msg.message.data = json.dumps(payload_dict).encode('utf-8')
        return msg

    def _valid_payload(self, task_execution_try_id=1):
        return {
            'args': [],
            'kwargs': {},
            'meta_info': {
                'module_name': 'django_i3tasks.tests_tasks',
                'func_name': 'task_a',
                'task_execution_try_id': task_execution_try_id,
                'task_execution_id': 1,
                'bind': False,
                'encoding': 'utf-8',
            }
        }

    @patch('django_i3tasks.management.commands.i3tasks_worker.settings')
    @patch('django_i3tasks.management.commands.i3tasks_worker.PubSubSystemUtils')
    @patch('django_i3tasks.management.commands.i3tasks_worker.TaskExecutionTry')
    @patch('django_i3tasks.management.commands.i3tasks_worker.TaskObj')
    @patch('django_i3tasks.management.commands.i3tasks_worker.importlib')
    def test_successful_task_is_acknowledged(
        self, mock_importlib, MockTaskObj, MockTry, MockPubSub, mock_settings
    ):
        from django_i3tasks.types import PullQueue
        mock_settings.I3TASKS.default_queue = MagicMock()
        mock_settings.I3TASKS.default_queue.queue_name = 'default'
        mock_settings.I3TASKS.other_queues = [PullQueue('heavy', 'heavy-pull')]
        mock_settings.PUBSUB_CONFIG = {'PROJECT_ID': 'test-project'}

        mock_utils = MagicMock()
        MockPubSub.return_value = mock_utils

        msg = self._make_message(self._valid_payload())
        # First call returns one message, second raises KeyboardInterrupt to exit loop
        mock_utils.pull_messages.side_effect = [[msg], KeyboardInterrupt]

        mock_task = MagicMock()
        mock_importlib.import_module.return_value = mock_task
        MockTry.objects.get.return_value = MagicMock(task_execution_id=1)

        from django_i3tasks.management.commands.i3tasks_worker import Command
        cmd = Command()
        try:
            cmd.handle(queue='heavy')
        except KeyboardInterrupt:
            pass

        mock_utils.acknowledge.assert_called_once_with(['ack-123'])

    @patch('django_i3tasks.management.commands.i3tasks_worker.settings')
    @patch('django_i3tasks.management.commands.i3tasks_worker.PubSubSystemUtils')
    def test_malformed_message_is_not_acknowledged(self, MockPubSub, mock_settings):
        from django_i3tasks.types import PullQueue
        mock_settings.I3TASKS.default_queue = MagicMock()
        mock_settings.I3TASKS.default_queue.queue_name = 'default'
        mock_settings.I3TASKS.other_queues = [PullQueue('heavy', 'heavy-pull')]
        mock_settings.PUBSUB_CONFIG = {'PROJECT_ID': 'test-project'}

        mock_utils = MagicMock()
        MockPubSub.return_value = mock_utils

        bad_msg = MagicMock()
        bad_msg.ack_id = 'ack-bad'
        bad_msg.message.data = b'not valid json{'

        mock_utils.pull_messages.side_effect = [[bad_msg], KeyboardInterrupt]

        from django_i3tasks.management.commands.i3tasks_worker import Command
        cmd = Command()
        try:
            cmd.handle(queue='heavy')
        except KeyboardInterrupt:
            pass

        mock_utils.acknowledge.assert_not_called()

    @patch('django_i3tasks.management.commands.i3tasks_worker.settings')
    @patch('django_i3tasks.management.commands.i3tasks_worker.PubSubSystemUtils')
    @patch('django_i3tasks.management.commands.i3tasks_worker.TaskExecutionTry')
    @patch('django_i3tasks.management.commands.i3tasks_worker.TaskObj')
    @patch('django_i3tasks.management.commands.i3tasks_worker.importlib')
    def test_max_retries_exceeded_is_acknowledged(
        self, mock_importlib, MockTaskObj, MockTry, MockPubSub, mock_settings
    ):
        from django_i3tasks.types import PullQueue
        from django_i3tasks.exceptions import MaxRetriesExceededError
        mock_settings.I3TASKS.default_queue = MagicMock()
        mock_settings.I3TASKS.default_queue.queue_name = 'default'
        mock_settings.I3TASKS.other_queues = [PullQueue('heavy', 'heavy-pull')]
        mock_settings.PUBSUB_CONFIG = {'PROJECT_ID': 'test-project'}

        mock_utils = MagicMock()
        MockPubSub.return_value = mock_utils

        msg = self._make_message(self._valid_payload())
        mock_utils.pull_messages.side_effect = [[msg], KeyboardInterrupt]

        mock_task = MagicMock()
        mock_importlib.import_module.return_value = mock_task
        MockTry.objects.get.return_value = MagicMock(task_execution_id=1)

        mock_task_obj = MagicMock()
        mock_task_obj.run_from_async.side_effect = MaxRetriesExceededError("max retries")
        MockTaskObj.return_value = mock_task_obj

        from django_i3tasks.management.commands.i3tasks_worker import Command
        cmd = Command()
        try:
            cmd.handle(queue='heavy')
        except KeyboardInterrupt:
            pass

        mock_utils.acknowledge.assert_called_once_with(['ack-123'])
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
python manage.py test django_i3tasks.tests_pull_worker.WorkerCommandValidationTest django_i3tasks.tests_pull_worker.WorkerLoopTest -v 2
```

Expected: FAIL — module `i3tasks_worker` doesn't exist.

- [ ] **Step 4: Create `i3tasks_worker.py`**

```python
# django_i3tasks/management/commands/i3tasks_worker.py
import json
import time
import logging
import importlib

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from django_i3tasks.exceptions import MaxRetriesExceededError
from django_i3tasks.models import TaskExecutionTry
from django_i3tasks.queue_manager.google_pubsub import PubSubSystemUtils
from django_i3tasks.types import PullQueue
from django_i3tasks.utils import TaskObj

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Pull tasks from a Pub/Sub pull subscription and execute them"

    def add_arguments(self, parser):
        parser.add_argument(
            '--queue',
            dest='queue',
            required=True,
            help='Name of the pull queue to consume (must be a PullQueue in I3TASKS)',
        )

    def handle(self, *args, **options):
        queue_name = options['queue']
        i3tasks = settings.I3TASKS

        all_queues = list(i3tasks.other_queues) + [i3tasks.default_queue]
        matched_queue = next((q for q in all_queues if q.queue_name == queue_name), None)

        if matched_queue is None:
            raise CommandError(f"Queue '{queue_name}' not found in I3TASKS configuration.")

        if not isinstance(matched_queue, PullQueue):
            raise CommandError(
                f"Queue '{queue_name}' is not a PullQueue. "
                "Pull worker can only consume PullQueue subscriptions."
            )

        pub_sub = PubSubSystemUtils(
            topic_name=matched_queue.queue_name,
            subscription_name=matched_queue.subscription_name,
        )

        logger.info(f"Starting pull worker for queue '{queue_name}' (subscription: {matched_queue.subscription_name})")
        self.stdout.write(f"Pull worker started for queue '{queue_name}'. Press Ctrl+C to stop.")

        while True:
            messages = pub_sub.pull_messages(max_messages=1)

            if not messages:
                time.sleep(1)
                continue

            for received_message in messages:
                ack_id = received_message.ack_id
                try:
                    data = json.loads(received_message.message.data.decode('utf-8'))
                    meta_info = data['meta_info']
                except (json.JSONDecodeError, KeyError, UnicodeDecodeError) as exc:
                    logger.error(f"Failed to deserialize message {ack_id}: {exc}")
                    # Do not ack — Pub/Sub will redeliver
                    continue

                try:
                    task_module = importlib.import_module(meta_info['module_name'])
                    task = getattr(task_module, meta_info['func_name'])

                    task_execution_try = TaskExecutionTry.objects.get(
                        id=meta_info['task_execution_try_id']
                    )
                    task_obj = TaskObj(
                        task_execution_id=task_execution_try.task_execution_id,
                        encoding=task.encoding,
                        max_retries=task.max_retries,
                        pubsub_system_utils=task.pubsub_system_utils,
                        pubsub_task_utils=task.pubsub_task_utils,
                    )
                    task_obj.run_from_async(
                        task_execution_try_id=meta_info['task_execution_try_id']
                    )
                except MaxRetriesExceededError:
                    logger.warning(f"Max retries exceeded for message {ack_id}, acknowledging.")
                except Exception as exc:
                    logger.error(f"Unexpected error processing message {ack_id}: {exc}", exc_info=True)

                # Reached only if deserialization succeeded (the `continue` above skips this)
                pub_sub.acknowledge([ack_id])
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python manage.py test django_i3tasks.tests_pull_worker.WorkerCommandValidationTest django_i3tasks.tests_pull_worker.WorkerLoopTest -v 2
```

Expected: All tests PASS.

- [ ] **Step 6: Run full test suite**

```bash
python manage.py test django_i3tasks -v 2
```

Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add django_i3tasks/management/commands/i3tasks_worker.py django_i3tasks/tests_pull_worker.py
git commit -m "feat: add i3tasks_worker management command for pull queue consumption"
```

---

## Task 6: Update README user documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the imports section**

In the "Configure settings" subsections, update the import line from:
```python
from django_i3tasks.types import I3TasksSettings, Queue, Schedule
```
to:
```python
from django_i3tasks.types import I3TasksSettings, PushQueue, PullQueue, Queue, Schedule
```

- [ ] **Step 2: Add a "Pull queues (worker mode)" section after the existing settings section**

Add after the `### 5. Ensure Pub/Sub topics and subscriptions exist` section:

````markdown
---

## Pull queues (worker mode)

By default, tasks are delivered via Pub/Sub **push** — Pub/Sub calls your `/i3/tasks-push/` endpoint. This requires an HTTP endpoint reachable from Pub/Sub.

For environments without a public endpoint (local development, private networks), use a **pull queue**: a background worker process actively polls Pub/Sub for messages.

### Configure a pull queue

Use `PullQueue` instead of `PushQueue` (or `Queue`) in `other_queues`:

```python
from django_i3tasks.types import I3TasksSettings, PushQueue, PullQueue, Queue, Schedule

I3TASKS = I3TasksSettings(
    namespace="tasks.myproject",
    default_queue=PushQueue(           # push — requires HTTP endpoint
        queue_name="default",
        subscription_name="default",
        push_endpoint="http://HOST/i3/tasks-push/",
    ),
    other_queues=(
        PullQueue(                     # pull — worker polls this subscription
            queue_name="heavy",
            subscription_name="heavy-pull",
        ),
    ),
    schedules=(),
)
```

> **Note:** `Queue` is an alias for `PushQueue` — existing configurations need no changes.

> **Note:** `default_queue` must remain a `PushQueue`. The `/i3/tasks-push/` view requires it.

### Create Pub/Sub resources

Run `i3tasks_ensure_pubsub` as usual — it automatically creates pull subscriptions (without a push endpoint) for `PullQueue` entries:

```bash
python manage.py i3tasks_ensure_pubsub
```

### Start the worker

```bash
python manage.py i3tasks_worker --queue=heavy
```

The worker runs in a loop, pulling one message at a time, executing the task, and acknowledging it. Stop it with `Ctrl+C`.

### Retry behaviour

Retry logic is identical to push: on failure, the task is re-enqueued (published back to the topic) up to `default_max_retries` times. The worker always acknowledges after `run_from_async` completes, whether the task succeeded, retried, or exhausted retries.

Only malformed messages (unreadable JSON, missing fields) are not acknowledged — Pub/Sub will redeliver them.

### Assigning tasks to a pull queue

Use `@TaskDecorator` with `topic_name` pointing to the pull queue's topic:

```python
from django_i3tasks.utils import TaskDecorator

@TaskDecorator(topic_name='heavy')
def heavy_task(data):
    ...

heavy_task.delay(data)
```

The worker consuming the `heavy` pull queue will pick it up.
````

- [ ] **Step 3: Update the `I3TasksSettings` reference table**

Add a note under `default_queue`:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `namespace` | `str` | required | Prefix for Pub/Sub topic/subscription names |
| `default_queue` | `PushQueue` | required | Default push queue — must be `PushQueue` |
| `other_queues` | `tuple[PushQueue \| PullQueue]` | `()` | Additional queues; accepts both push and pull |
| `schedules` | `tuple[Schedule]` | `()` | Scheduled tasks (cron-based) |
| `force_sync` | `bool` | `False` | If `True`, `.delay()` runs synchronously (useful for testing) |
| `default_max_retries` | `int` | `3` | Maximum retry attempts on failure |
| `run_queue_create_command_on_startup` | `bool` | `True` | Auto-run `i3tasks_ensure_pubsub` on app startup |

- [ ] **Step 4: Verify README renders correctly**

```bash
python -c "
import re
with open('README.md') as f:
    content = f.read()
assert 'PullQueue' in content
assert 'i3tasks_worker' in content
assert 'PushQueue' in content
print('README OK')
"
```

Expected: `README OK`

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: document pull queues and i3tasks_worker in README"
```

---

## Final check

- [ ] **Run complete test suite one last time**

```bash
python manage.py test django_i3tasks -v 2
```

Expected: All tests PASS, no failures.
