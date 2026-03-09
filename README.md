# django-i3tasks

Django app for managing async tasks via HTTP using Google Cloud Pub/Sub.

```
pip install django-i3tasks
```

---

## Quick start

### 1. Add to `INSTALLED_APPS`

```python
INSTALLED_APPS = [
    ...,
    "django_i3tasks",
]
```

### 2. Include the URL configuration

```python
# urls.py
from django.urls import path, include

urlpatterns = [
    ...,
    path("i3/", include("django_i3tasks.urls")),
]
```

This registers two endpoints:
- `POST /i3/tasks-push/` — receives tasks pushed by Pub/Sub
- `POST /i3/tasks-beat/` — triggered by an external scheduler (e.g. Google Cloud Scheduler) to run scheduled tasks

### 3. Run migrations

```bash
python manage.py migrate
```

This creates the tables for task executions, attempts, and results.

### 4. Configure settings

#### Local / emulator

```python
from django_i3tasks.types import I3TasksSettings, Queue, Schedule

PUBSUB_CONFIG = {
    "EMULATOR": True,
    "HOST": "localhost:8085",       # or named host in Docker Compose
    "PROJECT_ID": "my-project",
    "CREDENTIALS": False,
}

I3TASKS = I3TasksSettings(
    namespace=f"tasks.{SHORT_PROJECT_NAME}",
    default_queue=Queue(
        queue_name="default",
        subscription_name="default",
        push_endpoint="http://localhost:8000/i3/tasks-push/",
    ),
    other_queues=(),
    schedules=(
        Schedule(
            module_name="myapp.tasks",
            func_name="my_scheduled_task",
            cron="* * * * *",
            args=[],
            kwargs={},
        ),
    ),
)
```

#### Production (Google Cloud)

```python
from django_i3tasks.types import I3TasksSettings, Queue, Schedule

PUBSUB_CONFIG = {
    "EMULATOR": False,
    "PROJECT_ID": "my-project",
    "CREDENTIALS": "/app/conf/credentials.json",  # path to service account JSON
}

I3TASKS = I3TasksSettings(
    namespace=f"tasks.{SHORT_PROJECT_NAME}",
    default_queue=Queue(
        queue_name="default",
        subscription_name="default",
        push_endpoint="https://your-host.example.com/i3/tasks-push/",
    ),
    other_queues=(),
    schedules=(),
)
```

### 5. Ensure Pub/Sub topics and subscriptions exist

Run this once to create the required Pub/Sub resources:

```bash
python manage.py i3tasks_ensure_pubsub
```

This is also called automatically on startup if `run_queue_create_command_on_startup=True` (the default).

---

## Defining tasks

Decorate any function with `@TaskDecorator` to make it an async task:

```python
# myapp/tasks.py
from django_i3tasks.utils import TaskDecorator

@TaskDecorator
def send_email(recipient, subject, body):
    # your logic here
    pass
```

### Running a task asynchronously

```python
from myapp.tasks import send_email

send_email.delay("user@example.com", "Hello", "World")
# or equivalently:
send_email.async_run("user@example.com", "Hello", "World")
```

### Running a task synchronously

```python
send_email.sync_run("user@example.com", "Hello", "World")
# or call it directly:
send_email("user@example.com", "Hello", "World")
```

### Accessing task metadata inside the function (`bind`)

When `bind=True`, the task receives itself as `task_metadata`:

```python
@TaskDecorator(bind=True)
def my_task(arg1, task_metadata=None):
    print(task_metadata)  # TaskObj instance
```

---

## `I3TasksSettings` reference

| Parameter | Type | Default | Description |
|---|---|---|---|
| `namespace` | `str` | required | Prefix for Pub/Sub topic/subscription names |
| `default_queue` | `Queue` | required | Default queue configuration |
| `other_queues` | `tuple[Queue]` | `()` | Additional queues |
| `schedules` | `tuple[Schedule]` | `()` | Scheduled tasks (cron-based) |
| `force_sync` | `bool` | `False` | If `True`, `.delay()` runs synchronously (useful for testing) |
| `default_max_retries` | `int` | `3` | Maximum retry attempts on failure |
| `run_queue_create_command_on_startup` | `bool` | `True` | Auto-run `i3tasks_ensure_pubsub` on app startup |

---

## How it works

1. `.delay()` serializes the task and publishes it to Google Cloud Pub/Sub.
2. A `TaskExecution` and a `TaskExecutionTry` record are saved to the database.
3. The Pub/Sub push subscription delivers the message to `/i3/tasks-push/`.
4. The endpoint deserializes and executes the task, saving the result.
5. On failure, the task is re-enqueued up to `default_max_retries` times.

Scheduled tasks are triggered by hitting `/i3/tasks-beat/`. The app evaluates each configured `Schedule`'s cron expression and runs matching tasks.
