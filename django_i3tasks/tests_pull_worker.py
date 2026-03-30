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
