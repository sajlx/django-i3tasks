# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`django-i3tasks` is a reusable Django app for managing asynchronous tasks via HTTP requests using Google Cloud Pub/Sub. It is distributed as a pip package and meant to be installed in other Django projects.

## Commands

```bash
# Create virtual environment
make virtualenv_create

# Install for development
pip install -e .

# Run tests
python manage.py test django_i3tasks

# Build distribution package
make package_build

# Upload to PyPI
make package_upload
```

Dependencies: Django, djangorestframework, requests, croniter>=2.0.1

## Architecture

### Task Execution Flow

1. Functions decorated with `@TaskDecorator` gain `.delay()` and `.async_run()` methods.
2. Calling `.delay()` serializes the task and enqueues it to Google Cloud Pub/Sub.
3. A `TaskExecution` (metadata) and `TaskExecutionTry` (attempt) record are created in the DB.
4. The Pub/Sub push subscription delivers the task payload to the `/i3/tasks-push/` endpoint.
5. `PushedTaskView` deserializes and executes the task, saving results in `TaskExecutionResult`.
6. On failure, retry logic re-enqueues (up to `default_max_retries`).

### Scheduled Tasks Flow

1. An external scheduler (e.g., Google Cloud Scheduler) periodically hits `/i3/tasks-beat/`.
2. `BeatTaskView` evaluates cron expressions (via `croniter`) against the current time.
3. Matching schedules are executed synchronously or enqueued asynchronously.

### Key Modules

- **`django_i3tasks/utils.py`**: Core logic — `TaskDecorator`, `TaskObj` (task lifecycle), `TaskTryObj` (attempt handling), `PubSubTaskUtils` (Pub/Sub serialization/enqueue).
- **`django_i3tasks/models.py`**: `TaskExecution`, `TaskExecutionTry`, `TaskExecutionResult` — DB persistence layer.
- **`django_i3tasks/views.py`**: `PushedTaskView` (receives push from Pub/Sub), `BeatTaskView` (triggers scheduled tasks), `HealthTaskView` (`/i3/tasks-health/` aggregate probe), `TaskStatusView` (`/i3/tasks-status/<int:id>/` and `/<uuid:uuid>/` — single-task status). `TaskExecution` has both an integer PK and a public `uuid` field; `.delay()`/`.async_run()` return a `ChainHandle` exposing `.task_execution_id`, `.task_uuid`, `.task_execution`.
- **`django_i3tasks/queue_manager/google_pubsub.py`**: `PubSubSystemUtils` — manages Pub/Sub clients, topics, and subscriptions. Supports emulator and production.
- **`django_i3tasks/types.py`**: `Queue`, `Schedule`, `I3TasksSettings` dataclasses used for configuration.
- **`django_i3tasks/management/commands/i3tasks_ensure_pubsub.py`**: Management command that creates Pub/Sub topics/subscriptions on startup.

### Required Host Project Settings

```python
PUBSUB_CONFIG = {
    "EMULATOR": True,                   # False for production
    "HOST": "pub-sub-emu-host:9085",    # Emulator host (ignored in production)
    "PROJECT_ID": "my-gcp-project",
    "CREDENTIALS": False                # Or path to service account JSON
}

I3TASKS = I3TasksSettings(
    namespace="tasks.project_name",
    default_queue=Queue(
        queue_name="default",
        subscription_name="default",
        push_endpoint="http://HOST:PORT/i3/tasks-push/"
    ),
    other_queues=(),
    schedules=(
        Schedule(
            module_name='app.tasks',
            func_name='my_task',
            cron='* * * * *',
            args=[],
            kwargs={}
        ),
    )
)
```

### URL Registration (host project)

```python
urlpatterns += [path('i3/', include('django_i3tasks.urls'))]
```

### Package Distribution

- Version is in `setup.py` (canonical) and `_setup.cfg` (keep in sync).
- `make package_build` produces sdist and wheel in `dist/`.
- `make package_upload` pushes to PyPI (requires credentials).
