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

This registers these endpoints:
- `POST /i3/tasks-push/` — receives tasks pushed by Pub/Sub
- `POST /i3/tasks-beat/` — triggered by an external scheduler (e.g. Google Cloud Scheduler) to run scheduled tasks
- `GET  /i3/tasks-health/` — JSON health probe for external monitoring (see [Health endpoint](#health-endpoint))
- `GET  /i3/tasks-status/<id>/` and `GET /i3/tasks-status/<uuid>/` — status of a single task (see [Status endpoint](#status-endpoint))

### 3. Run migrations

```bash
python manage.py migrate
```

This creates the tables for task executions, attempts, and results.

### 4. Configure settings

#### Local / emulator

```python
from django_i3tasks.types import I3TasksSettings, PushQueue, Schedule

PUBSUB_CONFIG = {
    "EMULATOR": True,
    "HOST": "localhost:8085",       # or named host in Docker Compose
    "PROJECT_ID": "my-project",
    "CREDENTIALS": False,
}

I3TASKS = I3TasksSettings(
    namespace=f"tasks.{SHORT_PROJECT_NAME}",
    default_queue=PushQueue(
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

> **Note:** `Queue` remains available as a backward-compatible alias for `PushQueue`. Existing configurations that use `Queue(...)` continue to work without changes.

#### Production (Google Cloud)

```python
from django_i3tasks.types import I3TasksSettings, PushQueue, Schedule

PUBSUB_CONFIG = {
    "EMULATOR": False,
    "PROJECT_ID": "my-project",
    "CREDENTIALS": "/app/conf/credentials.json",  # path to service account JSON
}

I3TASKS = I3TasksSettings(
    namespace=f"tasks.{SHORT_PROJECT_NAME}",
    default_queue=PushQueue(
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

`delay()` / `async_run()` return a `ChainHandle` that exposes the identifiers of
the enqueued task, so you can persist them and later query its status:

```python
handle = send_email.delay("user@example.com", "Hello", "World")

handle.task_execution_id   # integer PK of the TaskExecution
handle.task_uuid           # public UUID of the TaskExecution
handle.task_execution      # the TaskExecution instance itself
```

Both identifiers can be passed to the [status endpoint](#status-endpoint)
(`/i3/tasks-status/<id>/` or `/i3/tasks-status/<uuid>/`).

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

## Task chaining

`.delay()` returns a `ChainHandle`. Use `.then()` to schedule a follow-up task that runs after the current one succeeds:

```python
from myapp.tasks import send_email, log_sent

send_email.delay("user@example.com", "Hello", "World").then(log_sent)
```

You can chain multiple steps:

```python
send_email.delay(...).then(step_two).then(step_three)
```

Each step is persisted to the database. If the original task is executed by Pub/Sub, the next step in the chain is enqueued automatically on success.

### `on_success` shorthand

For a single fixed follow-up, declare it on the decorator:

```python
@TaskDecorator(on_success=log_sent)
def send_email(recipient, subject, body):
    ...
```

Every `.delay()` call will automatically chain `log_sent` after a successful execution.

---

## Task groups (fan-out / join)

Use `TaskGroup` to fan out N parallel tasks and run a callback when all of them succeed.

### Basic usage

```python
from django_i3tasks.models import TaskGroup
from myapp.tasks import process_item, all_done

# 1. Create the group — declare the callback and the expected member count.
group = TaskGroup.create(callback=all_done, total_count=3)

# 2. Dispatch member tasks, passing the group via __i3group__.
for item in items:
    process_item.delay(item, __i3group__=group)
```

`all_done` is called automatically once all 3 members complete successfully. If any member exceeds its retry limit, the group is marked `failed` and the callback is never called.

### Callback with a chain

Use `build_chain()` to attach a chain to the callback without dispatching it immediately:

```python
from myapp.tasks import all_done, notify_admin

chain = all_done.build_chain().then(notify_admin)
group = TaskGroup.create(callback=chain, total_count=3)
```

When the join fires, `all_done` is called and `notify_admin` is chained after it.

### `TaskGroup` states

| Status | Meaning |
|--------|---------|
| `pending` | Waiting for members to complete |
| `success` | All members succeeded; callback dispatched |
| `failed` | At least one member exceeded retries |

---

## Pull queues

By default, tasks are delivered via Pub/Sub **push** — Pub/Sub calls your `/i3/tasks-push/` HTTP endpoint. For workers that cannot expose a public endpoint (local dev, private networks) or that need to control their own concurrency, you can use a **pull** queue instead.

Push and pull are mutually exclusive per queue. A queue is either one or the other.

### Configuring a pull queue

Add a `PullQueue` to `other_queues`. Pull queues do not require a push endpoint.

```python
from django_i3tasks.types import I3TasksSettings, PushQueue, PullQueue, Schedule

I3TASKS = I3TasksSettings(
    namespace="tasks.myproject",
    default_queue=PushQueue(
        queue_name="default",
        subscription_name="default",
        push_endpoint="https://your-host.example.com/i3/tasks-push/",
    ),
    other_queues=(
        PullQueue(
            queue_name="heavy",
            subscription_name="heavy-pull",
        ),
    ),
)
```

> **Note:** `default_queue` must always be a `PushQueue` — the `/i3/tasks-push/` view requires it. Only `other_queues` entries can be `PullQueue`.

### Dispatching a task to a pull queue

Pass the queue name when calling `.delay()`:

```python
@TaskDecorator(queue_name="heavy")
def heavy_task(data):
    ...

heavy_task.delay(data)
```

### Running the pull worker

Start a worker process for each pull queue you want to consume:

```bash
python manage.py i3tasks_worker --queue=heavy
```

The worker polls the subscription in a loop, processing one message at a time. Press Ctrl+C to stop.

**Ack / nack behavior:**
- Task succeeds → message is acknowledged
- Task exceeds max retries → message is acknowledged (no further delivery)
- Malformed message (bad JSON, missing fields) → message is **not** acknowledged; Pub/Sub redelivers after the ack deadline
- Unexpected infrastructure error → message is **not** acknowledged; Pub/Sub redelivers

Retries are managed by the task itself via Pub/Sub: on failure with retries remaining, a new attempt is published back to the topic. The worker always acknowledges after `run_from_async` returns (success or exhausted retries).

### Provisioning Pub/Sub resources

`i3tasks_ensure_pubsub` handles both push and pull queues. Pull subscriptions are created without a push endpoint:

```bash
python manage.py i3tasks_ensure_pubsub
```

---

## `I3TasksSettings` reference

| Parameter | Type | Default | Description |
|---|---|---|---|
| `namespace` | `str` | required | Prefix for Pub/Sub topic/subscription names |
| `default_queue` | `PushQueue` | required | Default push queue (must be `PushQueue`; required by the HTTP view) |
| `other_queues` | `tuple[PushQueue \| PullQueue]` | `()` | Additional queues — each can be a `PushQueue` or a `PullQueue` |
| `schedules` | `tuple[Schedule]` | `()` | Scheduled tasks (cron-based) |
| `force_sync` | `bool` | `False` | If `True`, `.delay()` runs synchronously (useful for testing) |
| `default_max_retries` | `int` | `3` | Maximum retry attempts on failure |
| `retry_minimum_backoff_seconds` | `int \| None` | `10` | Pub/Sub redelivery backoff floor. `None` on both backoff params leaves the subscription's retry policy unset (Pub/Sub then redelivers with near-zero backoff) |
| `retry_maximum_backoff_seconds` | `int \| None` | `600` | Pub/Sub redelivery backoff ceiling |
| `run_queue_create_command_on_startup` | `bool` | `True` | Auto-run `i3tasks_ensure_pubsub` on app startup |
| `health_token` | `str \| None` | `None` | If set, `/i3/tasks-health/` requires `Authorization: Bearer <token>` or `?token=<token>`; otherwise the endpoint is unauthenticated |
| `status_token` | `str \| None` | `None` | If set, `/i3/tasks-status/` requires `Authorization: Bearer <token>` or `?token=<token>`. Falls back to `health_token` when unset; otherwise the endpoint is unauthenticated |
| `health_window_minutes` | `int` | `60` | Time window over which `totals` and `by_task` aggregates are computed |
| `health_stuck_minutes` | `int` | `15` | A try with `started_at` older than this and not yet completed counts as "stuck running" |
| `health_failed_threshold` | `int` | `5` | Trigger `warning` when failed tries in the window exceed this number |
| `health_pending_age_seconds_threshold` | `int` | `300` | Trigger `critical` when the oldest pending try is older than this many seconds |

### Queue types

| Type | Fields | Delivery |
|------|--------|----------|
| `PushQueue(queue_name, subscription_name, push_endpoint)` | 3 fields | Pub/Sub pushes to your HTTP endpoint |
| `PullQueue(queue_name, subscription_name)` | 2 fields | Worker polls with `i3tasks_worker --queue=<name>` |
| `Queue` | alias for `PushQueue` | Backward-compatible; existing configs need no changes |

---

## Health endpoint

`GET /i3/tasks-health/` is a JSON probe that aggregates `TaskExecutionTry` rows so external monitoring tools (Uptime Kuma, GCP Uptime, Pingdom, custom dashboards, etc.) can tell whether the task system is healthy.

### Response shape

```json
{
  "status": "ok",                  // "ok" | "warning" | "critical"
  "now": "2026-05-03T10:22:08+00:00",
  "window_minutes": 60,
  "thresholds": {
    "stuck_minutes": 15,
    "failed_threshold": 5,
    "pending_age_seconds_threshold": 300
  },
  "totals": {                      // counts of TaskExecutionTry within the window
    "pending": 0,                  // started_at IS NULL, is_completed=False
    "running": 0,                  // started_at set, is_completed=False
    "success": 340,                // is_completed=True, is_success=True
    "failed":  5                   // is_completed=True, is_success=False
  },
  "stuck_running": 0,              // running for longer than stuck_minutes (no time-window cap)
  "oldest_pending_age_seconds": 0, // age of the oldest pending try in seconds (no time-window cap)
  "problems": [],                  // human-readable list of triggered conditions
  "by_task": [                     // top 50 task paths in the window, ordered by failed desc, success desc
    {
      "task_path": "app.tasks.send_email",
      "task_name": "send_email",
      "success": 20, "failed": 3, "running": 0, "pending": 0
    }
  ]
}
```

### Status logic

| `status`   | When                                                                                              | HTTP |
|------------|---------------------------------------------------------------------------------------------------|------|
| `critical` | `stuck_running > 0` **or** `oldest_pending_age_seconds > pending_age_seconds_threshold`           | 503  |
| `warning`  | failed tries in the window > `failed_threshold` (and no critical condition)                       | 200  |
| `ok`       | none of the above                                                                                 | 200  |

`stuck_running` and `oldest_pending_age_seconds` are computed across *all* unfinished tries, not only those inside `window_minutes` — a hung worker can outlast the window.

### Authentication

By default the endpoint is unauthenticated (suitable behind a private network or VPC). To require a shared secret, set `health_token` in `I3TasksSettings`:

```python
I3TASKS = I3TasksSettings(
    ...,
    health_token="a-long-random-string",
)
```

Then call the endpoint with either:

- header: `Authorization: Bearer a-long-random-string`, or
- query string: `?token=a-long-random-string`

Requests without (or with the wrong) token receive `401 Unauthorized`.

### Tuning thresholds

All thresholds are configurable via `I3TasksSettings` (see the reference table above). Pick values that reflect your workload:

```python
I3TASKS = I3TasksSettings(
    ...,
    health_window_minutes=15,                  # tighter window for chatty workloads
    health_stuck_minutes=5,                    # short tasks → flag hangs sooner
    health_failed_threshold=10,                # tolerate more transient failures
    health_pending_age_seconds_threshold=60,   # alert quickly on backlog
)
```

### Example: monitoring & dashboards

- **Uptime check (HTTP probe)** — point any HTTP monitor at `/i3/tasks-health/`. The 503 response on `critical` triggers the alert without parsing the body.
- **Custom dashboard** — poll the endpoint from your frontend / Grafana / internal admin: use `totals` for stacked bar charts, `by_task` for the "noisiest tasks" list, `problems` for a banner.
- **CLI quick check**:

  ```bash
  curl -fsS https://your-host.example.com/i3/tasks-health/ | jq '.status, .problems'
  ```

---

## Status endpoint

While the [health endpoint](#health-endpoint) reports on the task system as a
whole, the status endpoint reports on **one specific task**. Look it up either by
its integer PK or by its public UUID (both are returned at dispatch time from the
[`ChainHandle`](#running-a-task-asynchronously)):

```
GET /i3/tasks-status/<int:id>/
GET /i3/tasks-status/<uuid:uuid>/
```

### Response shape

```jsonc
{
  "status": "success",              // success | failed | running | pending | unknown
  "task": {
    "id": 42,
    "uuid": "6f1c2e0a-....",
    "task_name": "send_email",
    "task_path": "myapp.tasks",
    "task_args": ["user@example.com", "Hello", "World"],
    "task_kwargs": {},
    "task_group_id": null,
    "created_at": "2026-07-09T10:00:00+00:00",
    "updated_at": "2026-07-09T10:00:02+00:00"
  },
  "tries": [
    {
      "task_execution_try_id": 71,
      "try_number": 1,
      "asked_at": "2026-07-09T10:00:00+00:00",
      "started_at": "2026-07-09T10:00:01+00:00",
      "finished_at": "2026-07-09T10:00:02+00:00",
      "is_completed": true,
      "is_success": true,
      "result": { "ok": true }
    }
  ]
}
```

Returns `404` with `{"status": "not_found"}` when no task matches. The top-level
`status` collapses all attempts into one label: `success` if any try succeeded,
otherwise `failed` if the latest try completed, `running` if it started but has
not completed, `pending` if it was only enqueued, and `unknown` when there are no
tries yet.

### Authentication

Optional, mirroring the health endpoint. Set `status_token` (or reuse
`health_token`) on `I3TASKS` to require a token:

```python
I3TASKS = I3TasksSettings(
    # ...
    status_token="a-long-random-secret",
)
```

```bash
curl -H "Authorization: Bearer a-long-random-secret" \
  https://your-host.example.com/i3/tasks-status/42/
# or:  ?token=a-long-random-secret
```

When neither `status_token` nor `health_token` is set, the endpoint is
unauthenticated. Because the response includes task args, kwargs and results,
set a token if any of that is sensitive.

---

## How it works

**Push delivery (default):**
1. `.delay()` serializes the task and publishes it to Google Cloud Pub/Sub.
2. A `TaskExecution` and a `TaskExecutionTry` record are saved to the database.
3. The Pub/Sub push subscription delivers the message to `/i3/tasks-push/`.
4. The endpoint deserializes and executes the task, saving the result.
5. On failure, the task is re-enqueued up to `default_max_retries` times.

**Pull delivery (`PullQueue`):**
Steps 1–2 are identical. Instead of Pub/Sub pushing to an HTTP endpoint, the `i3tasks_worker` process polls the pull subscription and executes tasks in the same way.

Scheduled tasks are triggered by hitting `/i3/tasks-beat/`. The app evaluates each configured `Schedule`'s cron expression and runs matching tasks.
