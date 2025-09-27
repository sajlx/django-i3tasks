# django-i3tasks

## Django app for manage async tasks by http requests

to install
`pip install django-i3tasks`

---

## Quick start

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

   this can be changed depending by the trailing slash option that you put in your settings

3. Run `python manage.py migrate` to create the models.

   this create models where are save invocation and task tries and retries and task results

4. local example settings

   ```

   from django_i3tasks.types import I3TasksSettings, Queue, Schedule

   PUBSUB_CONFIG = {
       "EMULATOR": True,
       # "EMULATOR": False,
       "HOST": "pub-sub-emu-host:9085",  # depends localhost or named host in docker compose

       "PROJECT_ID": "i3idea", # Google project id
       "CREDENTIALS": False,
   }

   I3TASKS = I3TasksSettings(
       namespace=f"tasks.{SHORT_PROJECT_NAME}",
       default_queue=Queue(
           queue_name="default",
           subscription_name="default",
           push_endpoint="http://WORKER_HOST:PORT/i3/tasks-push/",
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

       "PROJECT_ID": "i3idea",  # Google project id
       "CREDENTIALS": "/app/conf/credential.json"  # path to json credential file
   }

   I3TASKS = I3TasksSettings(
       namespace=f"tasks.{SHORT_PROJECT_NAME}",
       default_queue=Queue(
           queue_name="default",
           subscription_name="default",
           push_endpoint="https://PRODUCTION_HOST_AND_PORT/i3/tasks-push/",
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
