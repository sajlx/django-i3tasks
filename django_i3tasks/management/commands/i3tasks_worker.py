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
                    pub_sub.acknowledge([ack_id])
                except MaxRetriesExceededError:
                    logger.warning(f"Max retries exceeded for message {ack_id}, acknowledging.")
                    pub_sub.acknowledge([ack_id])
                except Exception as exc:
                    logger.error(f"Unexpected error processing message {ack_id}: {exc}", exc_info=True)
                    # Do NOT acknowledge — Pub/Sub will redeliver
