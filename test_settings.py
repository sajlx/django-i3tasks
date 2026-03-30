# test_settings.py
import os
from django_i3tasks.types import I3TasksSettings, Queue

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django_i3tasks',
]

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

PUBSUB_CONFIG = {
    'EMULATOR': True,
    'HOST': 'localhost:9085',
    'PROJECT_ID': 'test-project',
    'CREDENTIALS': False,
}

I3TASKS = I3TasksSettings(
    namespace='test',
    default_queue=Queue(
        queue_name='default',
        subscription_name='default',
        push_endpoint='http://localhost:8000/i3/tasks-push/',
    ),
    other_queues=(),
    schedules=(),
    force_sync=True,
    default_max_retries=3,
    run_queue_create_command_on_startup=False,
)
