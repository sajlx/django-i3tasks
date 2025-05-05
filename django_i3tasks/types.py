
from collections import namedtuple
# from typing import NamedTuple

# class Person(NamedTuple):
#     name: str
#     age: int
#     height: float
#     weight: float
#     country: str = "Canada"


Queue = namedtuple('Queue', [
    'queue_name',
    'subscription_name',
    'push_endpoint'
])


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
            default_queue: Queue,
            other_queues: 'tuple[Queue, ...]',
            schedules: 'tuple[Schedule, ...]',
            force_sync: bool = False,
            default_max_retries: int = 3,
            run_queue_create_command_on_startup: bool = True
    ) -> None:
        self.namespace = namespace
        self.default_queue = default_queue
        self.other_queues = other_queues
        self.schedules = schedules
        self.force_sync = force_sync
        self.default_max_retries = default_max_retries
        self.run_queue_create_command_on_startup = run_queue_create_command_on_startup
