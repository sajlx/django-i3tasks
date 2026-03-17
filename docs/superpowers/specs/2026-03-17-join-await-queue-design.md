# Join / Chain System Design

**Date**: 2026-03-17
**Project**: django-i3tasks
**Status**: Approved

## Overview

Add a primitive coordination layer to django-i3tasks supporting two patterns:

1. **Chaining (Pipeline)**: Task B starts automatically when Task A completes successfully, optionally passing along a chain of further steps.
2. **Join (Fan-out)**: N tasks run in parallel; a callback task is dispatched only when all N complete successfully.

Failure handling is **fail-fast**: if any task fails (after exhausting retries), the chain/group is marked failed and subsequent tasks do not run.

## Chosen Approach

**Metadata chain + DB atomic group** (Approach A):

- Chain state is serialized into the `chain` field on `TaskExecution` and forwarded through each Pub/Sub message.
- Join coordination uses a new `TaskGroup` model with an atomic DB counter (`select_for_update`) to prevent double-firing the callback.
- No polling required; coordination is fully event-driven, triggered at task completion.

## Data Model Changes

### New model: `TaskGroup`

```python
class TaskGroup(CreatedUpdatedModel):
    callback_task_name = models.CharField(max_length=256)
    callback_task_path = models.CharField(max_length=256)
    callback_task_args = models.JSONField(default=list)
    callback_task_kwargs = models.JSONField(default=dict)

    total_count = models.IntegerField()
    completed_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)

    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED  = 'failed'
    status = models.CharField(max_length=16, default='pending')
```

The callback is stored as `(task_path, task_name, args, kwargs)` rather than a FK to `TaskExecution`, because the callback task is not created until all children complete.

### Modified model: `TaskExecution`

Two new nullable fields:

- `task_group = ForeignKey(TaskGroup, null=True, blank=True, on_delete=SET_NULL)` — membership in a join group.
- `chain = JSONField(null=True, blank=True)` — ordered list of remaining chain steps: `[{module_name, func_name, args, kwargs}, ...]`.

## Public API

### Chaining

Defined at dispatch time via `.then()`:

```python
task_a.delay(arg1).then(task_b, arg2).then(task_c, arg3)
```

`.then()` returns a chainable handle; it does not dispatch immediately. The full chain list is serialized into the first `TaskExecution.chain`.

Defined at decoration time via `on_success`:

```python
@task(on_success=task_b)
def task_a(...): ...
```

`on_success` is resolved at import time and prepended to the chain at dispatch. Both forms can be combined.

### Join / Fan-out

```python
group = TaskGroup.create(callback=task_aggregatore, args=[], kwargs={})
for item in items:
    task_process.delay(item, group=group)
```

`TaskGroup.create()` is a factory classmethod that builds and saves the group, recording `total_count = len(items)` after all children are dispatched (or passed as a parameter).

The callback can itself be the head of a chain:

```python
group = TaskGroup.create(callback=task_finalize.then(task_notify))
```

## Internal Mechanics

### Chaining flow

1. `.then(task_b, ...)` appends `{module_name, func_name, args, kwargs}` to a chain list held on the dispatch handle.
2. On `.delay()`, the full chain list is stored in `TaskExecution.chain` and included in `meta_info` sent via Pub/Sub.
3. In `TaskObj._run_from_db`, after a successful run:
   - If `chain` is non-empty, pop the first step.
   - Create a new `TaskExecution` with the remaining chain.
   - Dispatch the popped step.
4. `on_success` in the decorator is prepended to the chain at dispatch time.

### Join flow (atomic)

In `TaskObj._run_from_db`, after the task outcome is determined, if the `TaskExecution` belongs to a `TaskGroup`:

```
with transaction.atomic():
    group = TaskGroup.objects.select_for_update().get(pk=group_id)
    if failed:
        group.failed_count += 1
        group.status = FAILED
        group.save()
    else:
        group.completed_count += 1
        if group.failed_count == 0 and group.completed_count == group.total_count:
            group.status = SUCCESS
            group.save()
            should_dispatch_callback = True
        else:
            group.save()

if should_dispatch_callback:
    # dispatch outside transaction to avoid firing before DB commit
    dispatch_callback(group)
```

`should_dispatch_callback` is a local flag set inside the transaction block, used after commit to safely fire the callback exactly once.

### Fail fast

Once `failed_count > 0`, subsequent successful children still update `completed_count` but the condition `failed_count == 0` prevents the callback from ever being dispatched. The group permanently stays `FAILED`.

## Testing

### Unit tests (using `force_sync=True`)

- **Chaining basic**: A → B → C runs in order; `chain` field is correctly reduced at each step.
- **on_success + .then() combined**: decorator chain and dispatch-time chain merge correctly.
- **Join success**: N children all succeed → callback dispatched exactly once; `group.status == SUCCESS`.
- **Join fail fast**: one child fails → callback not dispatched; `group.status == FAILED`; remaining children completing do not re-trigger callback.
- **Join concurrency**: simulated concurrent completions using threads → callback dispatched exactly once (no double-fire).

### Integration tests

- End-to-end chain of 3 tasks via Pub/Sub emulator: verify `TaskExecution` records and result chain.
- End-to-end fan-out of 5 tasks + aggregator: verify group transitions to `SUCCESS` and callback `TaskExecution` is created.

## Out of Scope

- Await/polling API (caller blocking on task result) — not requested.
- Passing child results to the callback automatically — callback fetches results itself if needed.
- Modifying a chain or group after dispatch.
