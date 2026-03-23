# Pull Worker System — Design Spec

**Date:** 2026-03-23
**Branch:** improve-documentation
**Status:** Approved

## Overview

Add a pull-based worker system to `django-i3tasks` so that projects can choose, per queue, whether to use Pub/Sub push delivery (current model) or pull delivery (new). Push and pull are mutually exclusive per queue — a queue is either one or the other.

**Motivation:** Push requires an HTTP endpoint reachable by Pub/Sub. Pull enables local development, private networks, and worker-controlled concurrency without exposing a public endpoint.

---

## 1. Types and Configuration

Two explicit namedtuples replace the single `Queue` type:

```python
# django_i3tasks/types.py
PushQueue = namedtuple('PushQueue', ['queue_name', 'subscription_name', 'push_endpoint'])
PullQueue = namedtuple('PullQueue', ['queue_name', 'subscription_name'])

Queue = PushQueue  # backward-compatible alias
```

> **Note:** `Queue = PushQueue` means `repr()` of existing `Queue(...)` instances will show `PushQueue(...)`. This is purely cosmetic and does not affect behavior.

`I3TasksSettings.default_queue` must be a `PushQueue` (the push endpoint is required for the HTTP view). `other_queues` accepts either type.

**Example configuration:**

```python
I3TASKS = I3TasksSettings(
    namespace="tasks.myproject",
    default_queue=PushQueue(
        queue_name="default",
        subscription_name="default",
        push_endpoint="http://HOST/i3/tasks-push/",
    ),
    other_queues=(
        PullQueue(
            queue_name="heavy",
            subscription_name="heavy-pull",
        ),
    ),
)
```

---

## 2. Pub/Sub Subscription Creation

`PubSubSystemUtils.create_subscription()` and `i3tasks_ensure_pubsub` are updated to support both queue types.

**`create_subscription(queue)`** — takes the queue object:
- `PushQueue` → subscription created with `push_config` (existing behavior)
- `PullQueue` → subscription created without `push_config` (pull-mode subscription)

`isinstance(queue, PullQueue)` is used as the discriminator.

**`i3tasks_ensure_pubsub` command `handle()`** — currently accesses `.push_endpoint` unconditionally on all queues. Updated to:
- Skip `push_endpoint` access for `PullQueue` entries
- Call `create_subscription(queue)` passing the queue object so the correct type is used

---

## 3. PubSubSystemUtils Extensions

Two new methods on `PubSubSystemUtils`:

- `pull_messages(max_messages=1)` — calls `subscriber.pull(subscription=..., max_messages=max_messages)`, returns the list of `ReceivedMessage` objects
- `acknowledge(ack_ids)` — calls `subscriber.acknowledge(subscription=..., ack_ids=ack_ids)`

These use the existing `get_subscription_client()` and `get_subscription_name()` methods.

---

## 4. Management Command: `i3tasks_worker`

**Invocation:**

```bash
python manage.py i3tasks_worker --queue=heavy
```

**Arguments:**
- `--queue` (required) — queue name to consume

**Startup validation** — raises `CommandError` immediately if:
- `--queue` names an unknown queue
- The named queue is a `PushQueue` (pull worker cannot consume push subscriptions)

### Message Format

Pub/Sub pull delivers raw bytes in `received_message.message.data` (no HTTP envelope, no extra base64 wrapping). The bytes are UTF-8 encoded JSON produced by `PubSubTaskUtils.serialize`:

```json
{"args": [...], "kwargs": {...}, "meta_info": {"module_name": "...", "func_name": "...", "task_execution_try_id": 42, ...}}
```

Deserialization: `json.loads(message.data.decode('utf-8'))`.

### Task Execution

Mirrors `PushedTaskView.post()`:

```python
data = json.loads(message.data.decode('utf-8'))
meta_info = data['meta_info']

# 1. Import the decorated function (to get encoding, max_retries, pubsub_system_utils)
task_module = importlib.import_module(meta_info['module_name'])
task = getattr(task_module, meta_info['func_name'])  # TaskDecorator instance

# 2. Load TaskExecutionTry from DB
task_execution_try = TaskExecutionTry.objects.get(id=meta_info['task_execution_try_id'])

# 3. Construct TaskObj
task_obj = TaskObj(
    task_execution_id=task_execution_try.task_execution_id,
    encoding=task.encoding,
    max_retries=task.max_retries,
    pubsub_system_utils=task.pubsub_system_utils,
    pubsub_task_utils=task.pubsub_task_utils,
)

# 4. Execute
task_obj.run_from_async(task_execution_try_id=meta_info['task_execution_try_id'])
```

### Retry Strategy

`run_from_async` manages retries internally: on failure with retries remaining, it creates a new `TaskExecutionTry` row and re-publishes to the Pub/Sub **topic** (not the subscription). The worker therefore **always acknowledges** after `run_from_async` returns — whether it succeeded, retried, or raised `MaxRetriesExceededError`. Nacking is reserved only for deserialization failures (malformed messages), where re-delivery may succeed after a fix.

### Worker Loop

```
while True:
    messages = pull_messages(max_messages=1)
    if no messages:
        sleep(1)
        continue

    for message in messages:
        try:
            deserialize message.data
            import task, load TaskExecutionTry, construct TaskObj
            task_obj.run_from_async(task_execution_try_id=...)
        except (json.JSONDecodeError, KeyError, TaskExecutionTry.DoesNotExist) as e:
            log error
            # do NOT acknowledge — nack by not acking, Pub/Sub redelivers
            continue
        except Exception as e:
            log error
            # run_from_async raised unexpectedly; acknowledge to avoid infinite loop

        acknowledge(message.ack_id)
```

The loop runs until `KeyboardInterrupt` (Ctrl+C / SIGINT). SIGTERM handling is not in scope for this iteration.

---

## 5. Files Changed

| File | Change |
|------|--------|
| `django_i3tasks/types.py` | Add `PushQueue`, `PullQueue`; alias `Queue = PushQueue` |
| `django_i3tasks/queue_manager/google_pubsub.py` | Add `pull_messages()`, `acknowledge()`; update `create_subscription()` to accept queue object and branch on type |
| `django_i3tasks/management/commands/i3tasks_ensure_pubsub.py` | Update `handle()` to use `isinstance` instead of unconditional `.push_endpoint` access |
| `django_i3tasks/management/commands/i3tasks_worker.py` | **New** — management command with pull loop |

**Unchanged:** `models.py`, `views.py`, `utils.py`, `chain.py`, `urls.py`, all migrations.

---

## 6. Backward Compatibility

- `Queue = PushQueue` alias ensures existing configurations need no changes.
- All existing push queues continue to work without modification.
- `PullQueue` omits `push_endpoint` — no endpoint required, no HTTP server needed.
- `default_queue` must remain a `PushQueue` (the existing `/i3/tasks-push/` view requires it).
