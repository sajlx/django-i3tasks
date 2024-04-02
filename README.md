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

4. Start the development server and visit the admin to create a poll.

5. Visit the ``/polls/`` URL to participate in the poll.