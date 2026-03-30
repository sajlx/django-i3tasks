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


from unittest.mock import MagicMock, patch
from django_i3tasks.queue_manager.google_pubsub import PubSubSystemUtils


class CreateSubscriptionTest(TestCase):

    def _make_system_utils(self, topic_name='heavy', subscription_name='heavy-pull'):
        with patch.object(PubSubSystemUtils, '__init__', lambda self, *args, **kw: None):
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
        # Must NOT have push_config set
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


class PullMessagesAcknowledgeTest(TestCase):

    def _make_system_utils(self, topic_name='heavy', subscription_name='heavy-pull'):
        with patch.object(PubSubSystemUtils, '__init__', lambda self, *args, **kw: None):
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
        self.assertTrue(
            any('heavy' in str(c) for c in MockPubSubSystemUtils.call_args_list)
        )
        # ensure_queue_exists and ensure_subscription were called on the instance
        mock_utils_instance.ensure_queue_exists.assert_called()
        mock_utils_instance.ensure_subscription.assert_called()


from django.core.management.base import CommandError


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
