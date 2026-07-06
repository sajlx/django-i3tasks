# django-i3tasks — Django app for managing async tasks via HTTP
# Copyright (C) 2024-2026 Ivan Bettarini
# Licensed under the GNU General Public License v3.0 or later.
# See LICENSE in the project root for full text.

from unittest.mock import MagicMock

from django.test import TestCase

from django_i3tasks.queue_manager import google_pubsub
from django_i3tasks.queue_manager.google_pubsub import PubSubSystemUtils


def _bare_utils():
    """Build a PubSubSystemUtils bypassing __init__ (needs no live settings)."""
    utils = PubSubSystemUtils.__new__(PubSubSystemUtils)
    utils._publisher_client = None
    utils._subscription_client = None
    return utils


class CloseTest(TestCase):

    def test_close_closes_subscriber_and_publisher(self):
        utils = _bare_utils()
        sub = MagicMock()
        pub = MagicMock()
        utils._subscription_client = sub
        utils._publisher_client = pub

        utils.close()

        sub.close.assert_called_once()
        pub.stop.assert_called_once()
        pub.transport.close.assert_called_once()
        # cached clients are dropped so a later call rebuilds fresh channels
        self.assertIsNone(utils._subscription_client)
        self.assertIsNone(utils._publisher_client)

    def test_close_is_idempotent_when_no_clients(self):
        utils = _bare_utils()
        # Must not raise even though nothing was ever opened.
        utils.close()
        utils.close()

    def test_close_never_raises_on_client_error(self):
        utils = _bare_utils()
        sub = MagicMock()
        sub.close.side_effect = RuntimeError("boom")
        utils._subscription_client = sub

        # Teardown swallows client errors so shutdown can't crash.
        utils.close()
        self.assertIsNone(utils._subscription_client)

    def test_context_manager_closes_on_exit(self):
        utils = _bare_utils()
        sub = MagicMock()
        utils._subscription_client = sub

        with utils as ctx:
            self.assertIs(ctx, utils)

        sub.close.assert_called_once()


class RegistryTest(TestCase):

    def test_close_all_clients_closes_live_instances(self):
        utils = _bare_utils()
        sub = MagicMock()
        utils._subscription_client = sub

        google_pubsub._LIVE_INSTANCES.add(utils)
        try:
            google_pubsub._close_all_clients()
        finally:
            google_pubsub._LIVE_INSTANCES.discard(utils)

        sub.close.assert_called_once()

    def test_close_all_clients_tolerates_failing_instance(self):
        broken = MagicMock()
        broken.close.side_effect = RuntimeError("boom")
        google_pubsub._LIVE_INSTANCES.add(broken)
        try:
            # Should not propagate the error.
            google_pubsub._close_all_clients()
        finally:
            google_pubsub._LIVE_INSTANCES.discard(broken)
