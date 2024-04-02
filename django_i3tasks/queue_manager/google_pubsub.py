# from decorators import debug, do_twice
# import json
# import time
# import functools
import logging
# import inspect
# import datetime
import os
import google

from google.oauth2 import service_account
from google.cloud import pubsub_v1

from django.conf import settings

from django_i3tasks.types import I3TasksSettings
from django_i3tasks.types import Queue


logger = logging.getLogger(__name__)

REGITERED_TASKS = dict()


def get_default_queue_setting(param, default):
    I3TASKS = getattr(settings, 'I3TASKS', None)
    default_queue = getattr(I3TASKS, 'default_queue', None)
    _param = getattr(default_queue, param, default)
    return _param


class PubSubSystemUtils:
    def __init__(
        self,
        project_id=settings.PUBSUB_CONFIG.get("PROJECT_ID", None),
        topic_name=get_default_queue_setting("queue_name", "default"),
        subscription_name=get_default_queue_setting("subscription_name", "default"),
        encoding="utf-8",  # 'utf-32',
    ):
        assert project_id, "project_id for pubsub settings tasks must be set"
        self.project_id = project_id
        self.topic_name = topic_name
        self.subscription_name = subscription_name

        self.pubsub_host = settings.PUBSUB_CONFIG.get("HOST", None)
        if settings.PUBSUB_CONFIG.get("EMULATOR", False):
            assert self.pubsub_host, "host for pubsub settings tasks must be set"
            os.environ["PUBSUB_EMULATOR_HOST"] = self.pubsub_host
            os.environ["PUBSUB_PROJECT_ID"] = self.project_id

        self._publisher_client = None
        self._subscription_client = None

        # os.se PUBSUB_EMULATOR_HOST
        # PUBSUB_PROJECT_ID

        self._queue_already_exists = None
        self._subscription_already_exists = None

        self.namespace = getattr(settings.I3TASKS, "namespace", "default-namespace")

        self.encoding = encoding

    def get_publisher_client(self):
        if self._publisher_client is not None:
            return self._publisher_client
        publisher = None
        if settings.PUBSUB_CONFIG.get("EMULATOR", False):
            if not settings.PUBSUB_CONFIG.get("CREDENTIALS", None):
                publisher = pubsub_v1.PublisherClient()
            else:
                credentials = service_account.Credentials.from_service_account_file(
                    settings.PUBSUB_CONFIG.get("CREDENTIALS", None)
                )
                publisher = pubsub_v1.PublisherClient(credentials=credentials)
        else:
            # credentials = service_account.Credentials.from_service_account_file(
            #     settings.GOOGLE_SERVICE_ACCOUNT_FILE,
            #     scopes=settings.GOOGLE_SLIDES_SCOPES
            # )

            credentials = service_account.Credentials.from_service_account_file(
                settings.PUBSUB_CONFIG.get("CREDENTIALS", None)
            )
            publisher = pubsub_v1.PublisherClient(credentials=credentials)

        self._publisher_client = publisher

        return publisher

    def get_subscription_client(self):
        if self._subscription_client is not None:
            return self._subscription_client
        subscription = None
        if settings.PUBSUB_CONFIG.get("EMULATOR", False):
            subscription = pubsub_v1.SubscriberClient()
        else:
            # credentials = service_account.Credentials.from_service_account_file(
            #     settings.GOOGLE_SERVICE_ACCOUNT_FILE,
            #     scopes=settings.GOOGLE_SLIDES_SCOPES
            # )

            credentials = service_account.Credentials.from_service_account_file(
                settings.PUBSUB_CONFIG.get("CREDENTIALS", None)
            )
            subscription = pubsub_v1.SubscriberClient(credentials=credentials)

        self._subscription_client = subscription

        return subscription

    def get_topic_name(self):
        pub_client = self.get_publisher_client()
        topic_path = pub_client.topic_path(
            self.project_id,
            ".".join([self.namespace, self.topic_name.replace(".", "-")]),
        )
        # topic_name = 'projects/{project_id}/topics/{topic}'.format(
        #     project_id=self.project_id,
        #     topic=self.topic_name,  # Set this to something appropriate.
        # )
        # return topic_name
        return topic_path

    def get_subscription_name(self):
        sub_client = self.get_subscription_client()
        sub_path = sub_client.subscription_path(
            self.project_id,
            ".".join(
                [
                    self.namespace,
                    self.topic_name.replace(".", "-"),
                    self.subscription_name.replace(".", "-"),
                ]
            ),
        )
        # topic_name = 'projects/{project_id}/topics/{topic}'.format(
        #     project_id=self.project_id,
        #     topic=self.topic_name,  # Set this to something appropriate.
        # )
        # return topic_name
        return sub_path

    def queue_already_exists(self, force_check=False):
        if self._queue_already_exists is not None and not force_check:
            return self._queue_already_exists

        topic_name = self.get_topic_name()
        publisher = self.get_publisher_client()

        project_path = f"projects/{self.project_id}"

        topics = list(publisher.list_topics(request={"project": project_path}))
        for topic in topics:
            mex = f"Exisisting {topic}"
            logger.info(mex)

        self._queue_already_exists = topic_name in topics
        return self._queue_already_exists

    def ensure_queue_exists(self, force_check=False):
        if not self.queue_already_exists(force_check):
            self.create_queue()

    def create_queue(self):
        pub_client = self.get_publisher_client()
        topic_name = self.get_topic_name()

        try:
            logger.info(f"Try creating topic {topic_name}")  # noqa: W1203
            pub_client.create_topic(request={"name": topic_name})
            logger.info(f"Topic {topic_name} created")  # noqa:
            self._queue_already_exists = True
        except google.api_core.exceptions.AlreadyExists:
            logger.info(f"Topic {topic_name} already exists")  # noqa
            self._queue_already_exists = True
            # logger.info(exc)

        self.ensure_subscription()

    def list_subscriptions(self):
        topic_name = self.get_topic_name()
        publisher = self.get_publisher_client()

        # project_path = f"projects/{self.project_id}"

        publisher.list_topic_subscriptions(topic=topic_name)

        subscriptions = list(publisher.list_topic_subscriptions(topic=topic_name))
        return subscriptions

    def subscription_already_exists(
        self,
        force_check=False,
    ):
        if self._subscription_already_exists is not None and not force_check:
            return self._subscription_already_exists

        subscriptions = self.list_subscriptions()

        for suscription in subscriptions:
            mex = f"Exisisting {suscription}"
            logger.info(mex)

        self._subscription_already_exists = self.subscription_name in subscriptions
        return self._subscription_already_exists

    def create_subscription(self, endpoint=None):
        I3TASKS: I3TasksSettings = settings.I3TASKS
        subscriber = self.get_subscription_client()
        topic_name = self.get_topic_name()
        subscription_name = self.get_subscription_name()
        _endpoint = endpoint

        if not _endpoint:
            default_queue = I3TASKS.default_queue
            if topic_name == default_queue.queue_name:
                _endpoint = default_queue.push_endpoint
            else:
                queue: Queue =  None
                for _queue in I3TASKS.other_queues:
                    if topic_name == _queue.queue_name:
                        queue = _queue
                if queue is not None:
                    _endpoint = queue.push_endpoint
                else:
                    _endpoint = default_queue.push_endpoint

        try:
            subscriber.create_subscription(
                name=subscription_name,
                topic=topic_name,
                push_config=pubsub_v1.types.PushConfig(
                    push_endpoint=_endpoint
                ),
            )
            # future = subscriber.subscribe(subscription_name, callback)
        except google.api_core.exceptions.AlreadyExists:
            logger.info(f"Subscription {subscription_name} already exists")
            self._queue_already_exists = True

    def ensure_subscription(self, endpoint=None, force_check=False):
        if not self.subscription_already_exists(force_check):
            self.create_subscription()