# Pull Worker System — Design Spec

**Date:** 2026-03-23
**Branch:** improve-documentation
**Status:** Approved

## Overview

Add a pull-based worker system to `django-i3tasks` so that projects can choose, per queue, whether to use Pub/Sub push delivery (current model) or pull delivery (new). Push and pull are mutually exclusive per queue.

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

`I3TasksSettings.default_queue` and `I3TasksSettings.other_queues` accept either type. No other changes to `I3TasksSettings`.

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

`i3tasks_ensure_pubsub` and `PubSubSystemUtils.create_subscription()` are updated to inspect the queue type:

- `PushQueue` → subscription created with `push_config` (existing behavior)
- `PullQueue` → subscription created without `push_config` (pull-mode subscription)

`isinstance(queue, PullQueue)` is used as the discriminator.

---

## 3. PubSubSystemUtils Extensions

Two new methods on `PubSubSystemUtils`:

- `pull_messages(max_messages=1)` — calls `subscriber.pull()`, returns a list of received messages
- `acknowledge(ack_ids)` — calls `subscriber.acknowledge()` with the given ack IDs

These use the existing `get_subscription_client()` and `get_subscription_name()` methods.

---

## 4. Management Command: `i3tasks_worker`

**Invocation:**

```bash
python manage.py i3tasks_worker --queue=heavy
```

**Arguments:**
- `--queue` (required) — queue name to consume; must match a `PullQueue` in `I3TasksSettings`

**Worker loop (sequential, single-threaded):**

```
while True:
    messages = pull_messages(max_messages=1)
    if no messages:
        sleep(1)
        continue

    for message in messages:
        deserialize meta_info from message data
        try:
            TaskObj.run_from_async(task_execution_try_id=meta_info['task_execution_try_id'])
            acknowledge(message.ack_id)
        except MaxRetriesExceededError:
            acknowledge(message.ack_id)   # do not redeliver
        except Exception:
            nack (do not acknowledge → Pub/Sub redelivers)
            increment try_number in DB
```

The loop runs until `KeyboardInterrupt` (Ctrl+C / SIGINT).

**Startup validation:** The command raises `CommandError` immediately if:
- `--queue` names an unknown queue
- The named queue is a `PushQueue` (not consumable via pull)

---

## 5. Files Changed

| File | Change |
|------|--------|
| `django_i3tasks/types.py` | Add `PushQueue`, `PullQueue`; alias `Queue = PushQueue` |
| `django_i3tasks/queue_manager/google_pubsub.py` | Add `pull_messages()`, `acknowledge()`; update subscription creation logic |
| `django_i3tasks/management/commands/i3tasks_ensure_pubsub.py` | Use `isinstance` to choose push vs pull subscription |
| `django_i3tasks/management/commands/i3tasks_worker.py` | **New** — management command with pull loop |

**Unchanged:** `models.py`, `views.py`, `utils.py`, `chain.py`, `urls.py`, all migrations.

---

## 6. Backward Compatibility

- `Queue = PushQueue` alias ensures existing configurations need no changes.
- All existing push queues continue to work without modification.
- `PullQueue` omits `push_endpoint` — no endpoint needed, no HTTP server required.
