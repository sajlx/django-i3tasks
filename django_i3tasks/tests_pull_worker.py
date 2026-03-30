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
