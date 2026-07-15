# django-i3tasks — Django app for managing async tasks via HTTP
# Copyright (C) 2024-2026 Ivan Bettarini
# Licensed under the GNU General Public License v3.0 or later.
# See LICENSE in the project root for full text.

# from decorators import debug, do_twice
# import json
# import time
# import functools
import logging
# import inspect
# import datetime
import os
import atexit
import signal
import weakref
import google

from google.oauth2 import service_account
from google.cloud import pubsub_v1
from google.protobuf.duration_pb2 import Duration

from django.conf import settings

from django_i3tasks.types import I3TasksSettings
from django_i3tasks.types import PullQueue
from django_i3tasks.types import Queue


logger = logging.getLogger(__name__)

REGITERED_TASKS = dict()


def get_default_queue_setting(param, default):
    I3TASKS = getattr(settings, 'I3TASKS', None)
    default_queue = getattr(I3TASKS, 'default_queue', None)
    _param = getattr(default_queue, param, default)
    return _param


# --- Client teardown -------------------------------------------------------
# Every PubSubSystemUtils instance lazily opens gRPC channels for the
# publisher/subscriber clients. Nothing closes them on process shutdown, so
# under Django's autoreload each reload leaves dangling channels behind. We
# track live instances in a WeakSet and close their transports on exit
# (atexit) and on SIGTERM (containers/gunicorn), chaining any previous
# SIGTERM handler so we don't hijack the host app's shutdown.

_LIVE_INSTANCES = weakref.WeakSet()
_TEARDOWN_REGISTERED = False
_PREV_SIGTERM_HANDLER = None


def _close_all_clients():
    for inst in list(_LIVE_INSTANCES):
        try:
            inst.close()
        except Exception as exc:  # never let teardown crash shutdown
            logger.debug("Error closing PubSub clients on teardown: %s", exc)


def _sigterm_handler(signum, frame):
    _close_all_clients()
    prev = _PREV_SIGTERM_HANDLER
    if callable(prev) and prev not in (signal.SIG_IGN, signal.SIG_DFL):
        prev(signum, frame)
    else:
        # Restore default behaviour and re-raise so the process actually exits.
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)


def _register_teardown():
    global _TEARDOWN_REGISTERED, _PREV_SIGTERM_HANDLER
    if _TEARDOWN_REGISTERED:
        return
    _TEARDOWN_REGISTERED = True

    atexit.register(_close_all_clients)

    try:
        _PREV_SIGTERM_HANDLER = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, _sigterm_handler)
    except (ValueError, OSError):
        # signal.signal only works in the main thread; atexit still covers us.
        logger.debug("Could not install SIGTERM teardown handler (not main thread)")


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

        if getattr(settings.I3TASKS, "register_client_teardown", True):
            _LIVE_INSTANCES.add(self)
            _register_teardown()

    def close(self):
        """Close the gRPC transports of any cached Pub/Sub clients.

        Idempotent and defensive: tolerates client-library version
        differences and never raises, so it is safe to call from atexit /
        signal handlers.
        """
        sub = self._subscription_client
        if sub is not None:
            close_sub = getattr(sub, "close", None)
            if callable(close_sub):
                try:
                    close_sub()
                except Exception as exc:
                    logger.debug("Error closing subscriber client: %s", exc)
            self._subscription_client = None

        pub = self._publisher_client
        if pub is not None:
            # PublisherClient.stop() flushes pending batches and stops the
            # background commit threads; older/newer versions may expose
            # close() and/or an underlying transport instead.
            for method in ("stop", "close"):
                fn = getattr(pub, method, None)
                if callable(fn):
                    try:
                        fn()
                    except Exception as exc:
                        logger.debug("Error on publisher.%s(): %s", method, exc)
            transport = getattr(pub, "transport", None) or getattr(
                getattr(pub, "api", None), "transport", None
            )
            close_transport = getattr(transport, "close", None)
            if callable(close_transport):
                try:
                    close_transport()
                except Exception as exc:
                    logger.debug("Error closing publisher transport: %s", exc)
            self._publisher_client = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False

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

    def build_retry_policy(self):
        """Redelivery backoff for the subscription, or None to leave it unset.

        Pub/Sub's default is to redeliver with near-zero backoff, so a push
        endpoint that is refusing connections gets hammered indefinitely.
        """
        I3TASKS: I3TasksSettings = settings.I3TASKS
        minimum = getattr(I3TASKS, 'retry_minimum_backoff_seconds', 10)
        maximum = getattr(I3TASKS, 'retry_maximum_backoff_seconds', 600)
        if minimum is None and maximum is None:
            return None
        policy = pubsub_v1.types.RetryPolicy()
        if minimum is not None:
            policy.minimum_backoff = Duration(seconds=int(minimum))
        if maximum is not None:
            policy.maximum_backoff = Duration(seconds=int(maximum))
        return policy

    def create_subscription(self, endpoint=None):
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

        subscription = pubsub_v1.types.Subscription(
            name=subscription_name,
            topic=topic_name,
        )
        if not isinstance(matched_queue, PullQueue):
            _endpoint = endpoint or matched_queue.push_endpoint
            subscription.push_config = pubsub_v1.types.PushConfig(push_endpoint=_endpoint)

        retry_policy = self.build_retry_policy()
        if retry_policy is not None:
            subscription.retry_policy = retry_policy

        try:
            # The policy fields are only accepted through `request=`; the
            # flattened kwargs of create_subscription() do not carry them.
            subscriber.create_subscription(request=subscription)
        except google.api_core.exceptions.AlreadyExists:
            logger.info(f"Subscription {subscription_name} already exists")
            self._subscription_already_exists = True

    def ensure_subscription(self, endpoint=None, force_check=False):
        if not self.subscription_already_exists(force_check):
            self.create_subscription()

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
