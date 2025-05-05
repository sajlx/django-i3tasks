# django-i3tasks

Django app for manage async tasks by http requests
---
to install
`pip install django-i3tasks`
-----------

Quick start
-----------

1. Add "polls" to your INSTALLED_APPS setting like this::

    INSTALLED_APPS = [
        ...,
        "django_i3tasks",
    ]

2. Include the polls URLconf in your project urls.py like this::


    ```
    from django.urls import path

    from django_i3tasks import views as i3tasks_views

    path("i3/tasks-beat", i3tasks_views.BeatTaskView.as_view()),
    path("i3/tasks-beat/", i3tasks_views.BeatTaskView.as_view()),
    path("i3/tasks-push", i3tasks_views.PushedTaskView.as_view()),
    path("i3/tasks-push/", i3tasks_views.PushedTaskView.as_view()),
    ```

3. Run ``python manage.py migrate`` to create the models.

4. local example settings
    ```

    from django_i3tasks.types import I3TasksSettings, Queue, Schedule

    PUBSUB_CONFIG = {
        "EMULATOR": True,
        # "EMULATOR": False,
        "HOST": "pwd-pub-sub-emu:9085",

        # "NAMESPACE": "creators-area-back",
        # "DEFAULT_TOPIC_QUEUE_NAME": "default",
        # "DEFAULT_TOPIC_SUBSCRIPTION_NAME": "default",
        # "PUSH_ENDPOINT": "http://pwd-backend:9577/i3/tasks-push/",

        "PROJECT_ID": "i3idea",
        "CREDENTIALS": False,
        # "PROJECT_ID": 'hoopygang-158809',
        # "CREDENTIALS": "/app/service_accounts/creators-area-backend-pubsub.json"
    }

    I3TASKS = I3TasksSettings(
        namespace=f"tasks.{SHORT_PROJECT_NAME}",
        default_queue=Queue(
            queue_name="default",
            subscription_name="default",
            push_endpoint="http://pwd-backend:9577/i3/tasks-push/",
        ),
        other_queues=(

        ),
        schedules=(
            Schedule(
                module_name='django_i3tasks.tasks',
                func_name='test_task',
                cron='* * * * *',
                args=[],
                kwargs={},
            ),
        )
    )
    ```

5. production example settings
    ```

    from django_i3tasks.types import I3TasksSettings, Queue, Schedule

    PUBSUB_CONFIG = {
        # "EMULATOR": True,
        "EMULATOR": False,
        # "HOST": "pwd-pub-sub-emu:9085",

        # "NAMESPACE": "creators-area-back",
        # "DEFAULT_TOPIC_QUEUE_NAME": "default",
        # "DEFAULT_TOPIC_SUBSCRIPTION_NAME": "default",
        # "PUSH_ENDPOINT": "http://pwd-backend:9577/i3/tasks-push/",

        "PROJECT_ID": "i3idea",
        # "CREDENTIALS": True,
        # "PROJECT_ID": 'hoopygang-158809',
        "CREDENTIALS": "/app/conf/pwd-backend-pubsub.json"
    }

    I3TASKS = I3TasksSettings(
        namespace=f"tasks.{SHORT_PROJECT_NAME}",
        default_queue=Queue(
            queue_name="default",
            subscription_name="default",
            push_endpoint="https://prowodo-back-tasks-tqhjqw4diq-no.a.run.app/i3/tasks-push/",
        ),
        other_queues=(

        ),
        schedules=(
            Schedule(
                module_name='django_i3tasks.tasks',
                func_name='test_task',
                cron='* * * * *',
                args=[],
                kwargs={},
            ),
        )
    )
    ```