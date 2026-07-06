# django-i3tasks — Django app for managing async tasks via HTTP
# Copyright (C) 2024-2026 Ivan Bettarini
# Licensed under the GNU General Public License v3.0 or later.
# See LICENSE in the project root for full text.

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



# I3TASKS = {
#     "NAMESPACE": f"tasks.{SHORT_PROJECT_NAME}",
#     'QUEUES': {
#         'DEFAULT_QUEUE': {
#             "QUEUE_NAME": 'default',
#             "SUBSCRIPTION_NAME": 'default',
#             "PUSH_ENDPOINT": "http://pwd-backend:9577/i3/tasks-push/",
#         },
#         'OTHER_QUEUES': [

#         ]
#     },
#     'SCHEDULES': [
#         {
#             'module_name': 'i3tasks.tasks',
#             'func_name': 'test_task',
#             'cron': '* * * * *',
#             'args': [],
#             'kwargs': {},
#         },
#     ]
# }

# I3TasksSettings = namedtuple('I3TasksSettings', [
#     'namespace',
#     'queues',
#     'schedules'
# ])

class I3TasksSettings():
    namespace = 'itasks'
    default_queue = None
    other_queues = []
    schedules = []
    force_sync = False

    def __init__(
            self,
            namespace: str,
            default_queue: PushQueue,
            other_queues: 'tuple[PushQueue | PullQueue, ...]',
            schedules: 'tuple[Schedule, ...]',
            force_sync: bool = False,
            default_max_retries: int = 3,
            run_queue_create_command_on_startup: bool = True,
            register_client_teardown: bool = True,
            health_token: 'str | None' = None,
            health_window_minutes: int = 60,
            health_stuck_minutes: int = 15,
            health_failed_threshold: int = 5,
            health_pending_age_seconds_threshold: int = 300,
    ) -> None:
        self.namespace = namespace
        self.default_queue = default_queue
        self.other_queues = other_queues
        self.schedules = schedules
        self.force_sync = force_sync
        self.default_max_retries = default_max_retries
        self.run_queue_create_command_on_startup = run_queue_create_command_on_startup
        self.register_client_teardown = register_client_teardown
        self.health_token = health_token
        self.health_window_minutes = health_window_minutes
        self.health_stuck_minutes = health_stuck_minutes
        self.health_failed_threshold = health_failed_threshold
        self.health_pending_age_seconds_threshold = health_pending_age_seconds_threshold
