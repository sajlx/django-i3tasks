# -*- coding: utf-8 -*-

from logging import getLogger

# import mimesis

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from django_i3tasks.queue_manager.google_pubsub import PubSubSystemUtils

# from django_i3tasks.utils import PubSubSystemUtils

# from . import _create_data

# from core.models import MongoMainInfluencer

# mimesis_provider = mimesis.Generic('it')

logger = getLogger(__name__)


class Command(BaseCommand):
    help = "Ensure pubsub is well configured"

    def add_arguments(self, parser):

        parser.add_argument(
            '--only-print',
            dest='only_print',
            type=bool,
            help='Only print things to do without change anything',
            required=False,
            default=False
        )

        # parser.add_argument(
        #     '--mongo-id',
        #     dest='mongo_id',
        #     help='Mongo Id',
        #     required=False
        # )

    def handle(self, *args, **options):
        # if not settings.DEBUG:
        #     raise CommandError('Cannot execute inside non DEBUG Environments')
        only_print = options.get('only_print')
        logger.info('Ensure all pubsub is well configured...')
        logger.info(f'Only print is set to {only_print}')

        # postgres_id = options.get('postgres_id')

        # influencer = None

        # try:
        #     if mongo_id and postgres_id:
        #         influencer = MongoMainInfluencer.objects.get(id=mongo_id, postgres_id=postgres_id)
        #     elif mongo_id:
        #         influencer = MongoMainInfluencer.objects.get(id=mongo_id)
        #     elif postgres_id:
        #         influencer = MongoMainInfluencer.objects.get(postgres_id=postgres_id)
        #     else:
        #         raise CommandError('You must specify one id postgres or mongo')
        # except MongoMainInfluencer.DoesNotExist:
        #     raise CommandError('Influencer not found')

        # _create_data(influencer)
        try:
            pub_sub_system_utils = PubSubSystemUtils()
            pub_sub_system_utils.ensure_queue_exists()
            pub_sub_system_utils.ensure_subscription()
        except Exception as exc:
            logger.exception(exc)
            logger.error(f"Error on ensure default queue")
            return CommandError()


        for queue in settings.I3TASKS.other_queues:
            queue_name = None
            subscription_name = None
            push_endpoint = None

            try:
                queue_name = queue.queue_name
                subscription_name = queue.subscription_name
                push_endpoint = queue.push_endpoint
            except Exception as exc:
                logger.error(f"Error on getting params of other {queue_name} queue")
                logger.exception(exc)
                return CommandError()

            try:
                pub_sub_system_utils = PubSubSystemUtils(
                    topic_name=queue_name,
                    subscription_name=subscription_name,
                )
                pub_sub_system_utils.ensure_queue_exists()
                pub_sub_system_utils.ensure_subscription(push_endpoint)
            except Exception as exc:
                logger.error(f"Error on ensure {queue_name} queue")
                logger.exception(exc)
                return CommandError()

            # {
            #     "QUEUE_NAME": 'default',
            #     "SUBSCRIPTION_NAME": 'default',
            #     "PUSH_ENDPOINT": "http://pwd-backend:9577/i3/tasks-push/",
            # }
