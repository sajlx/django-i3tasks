# django-i3tasks — Django app for managing async tasks via HTTP
# Copyright (C) 2024-2026 Ivan Bettarini
# Licensed under the GNU General Public License v3.0 or later.
# See LICENSE in the project root for full text.

from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from .queue_manager import google_pubsub
from .types import I3TasksSettings, PushQueue

PROD_PUBSUB = {"EMULATOR": False, "PROJECT_ID": "p", "CREDENTIALS": False}


def _i3tasks(queue):
    return I3TasksSettings(
        namespace="test", default_queue=queue, other_queues=(), schedules=(),
        run_queue_create_command_on_startup=False, register_client_teardown=False,
    )


def _created_subscription(queue):
    """The Subscription that create_subscription sends, with the Pub/Sub client faked."""
    client = mock.Mock(subscription_path=lambda p, s: f"projects/{p}/subscriptions/{s}")
    with override_settings(PUBSUB_CONFIG=PROD_PUBSUB, I3TASKS=_i3tasks(queue)), \
            mock.patch.object(google_pubsub.pubsub_v1, "SubscriberClient", return_value=client), \
            mock.patch.object(google_pubsub.pubsub_v1, "PublisherClient", return_value=mock.Mock(
                topic_path=lambda p, t: f"projects/{p}/topics/{t}")):
        google_pubsub.PubSubSystemUtils(project_id="p").create_subscription()
    return client.create_subscription.call_args.kwargs["request"]


class PushAuthTest(SimpleTestCase):

    def test_a_queue_with_a_service_account_gets_an_oidc_push(self):
        queue = PushQueue("default", "default", "https://beat.example/i3/tasks-push/", "sa@p.iam.gserviceaccount.com")
        oidc = _created_subscription(queue).push_config.oidc_token
        self.assertEqual(oidc.service_account_email, "sa@p.iam.gserviceaccount.com")
        self.assertEqual(oidc.audience, "https://beat.example/i3/tasks-push/")

    def test_a_queue_without_one_keeps_an_unauthenticated_push(self):
        queue = PushQueue("default", "default", "https://beat.example/i3/tasks-push/")
        self.assertEqual(_created_subscription(queue).push_config.oidc_token.service_account_email, "")


class CredentialsTest(SimpleTestCase):

    def test_no_key_file_means_application_default_credentials(self):
        with override_settings(PUBSUB_CONFIG=PROD_PUBSUB):
            self.assertEqual(google_pubsub._credentials_kwargs(), {})
