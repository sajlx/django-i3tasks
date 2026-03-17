# Join / Chain System Design

**Date**: 2026-03-17
**Project**: django-i3tasks
**Status**: Approved

## Overview

Add a primitive coordination layer to django-i3tasks supporting two patterns:

1. **Chaining (Pipeline)**: Task B starts automatically when Task A completes successfully, passing along a chain of further steps.
2. **Join (Fan-out)**: N tasks run in parallel; a callback task is dispatched only when all N complete successfully.

Failure handling is **fail-fast**: if any task fails (after exhausting retries), the chain/group stops and subsequent tasks do not run.

## Chosen Approach

**Metadata chain + DB atomic group**:

- Chain state is stored in the `chain` field on `TaskExecution` (DB). Workers fetch it from DB at execution time — it is not embedded in the Pub/Sub message.
- Join coordination uses a new `TaskGroup` model with an atomic DB counter (`select_for_update`) to prevent double-firing the callback.
- No polling. Coordination is event-driven, triggered at task completion.

## Data Model Changes

### New model: `TaskGroup`

```python
class TaskGroup(CreatedUpdatedModel):
    # Callback stored as (path, name, args, kwargs) — same pattern as TaskExecution
    callback_task_name = models.CharField(max_length=256)   # func.__name__
    callback_task_path = models.CharField(max_length=256)   # inspect.getmodule(func).__name__
    callback_task_args = models.JSONField(default=list)      # must be JSON-serializable
    callback_task_kwargs = models.JSONField(default=dict)    # must be JSON-serializable
    callback_chain = models.JSONField(null=True, blank=True) # remaining chain after callback, or null
    # When dispatch_callback() fires, it creates a TaskExecution with chain=callback_chain

    total_count = models.IntegerField()
    completed_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)

    STATUS_PENDING = 'pending'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED  = 'failed'
    status = models.CharField(max_length=16, default='pending')

    class Meta:
        indexes = [models.Index(fields=['status'])]
```

`STATUS_RUNNING` is omitted — the group is either pending, done, or failed. No intermediate state is needed.

Special case: if `total_count=0`, the group is immediately considered `SUCCESS` and `dispatch_callback()` is called at creation time.

The callback `TaskExecution` is a normal, standalone record with no `task_group_id`. It is only created when the group reaches `SUCCESS`.

### Modified model: `TaskExecution`

Two new nullable fields:

```python
task_group = models.ForeignKey(
    TaskGroup, null=True, blank=True,
    on_delete=models.SET_NULL, related_name='members'
)
chain = models.JSONField(null=True, blank=True)
# chain format: [{module_name, func_name, args, kwargs}, ...]
# args/kwargs must be JSON-serializable (same constraint as task_args/task_kwargs)
```

Both fields are set at `TaskExecution` creation time. `task_group` is never changed after creation. `chain` may be updated by `_write_chain_to_db()` before dispatch but never after.

### Migrations

Standard Django migrations apply: `python manage.py makemigrations django_i3tasks`. No data migration needed; existing records have `task_group=NULL` and `chain=NULL`, which is valid.

## Public API

### Chaining

**Dispatch-time** via `.then()`:

```python
handle = task_a.delay(arg1)          # returns ChainHandle
handle.then(task_b, arg2)            # appends step, writes to DB, returns same handle
handle.then(task_c, arg3)            # etc.

# or fluently:
task_a.delay(arg1).then(task_b, arg2).then(task_c, arg3)
```

`.delay()` creates the `TaskExecution` and its first `TaskExecutionTry`, then wraps them in a `ChainHandle`. Each `.then()` call appends a step and immediately calls `_write_chain_to_db()` — it never holds state in memory only. Returns `self` for chaining.

Signature: `.then(task, *args, **kwargs) -> ChainHandle`

`*args` and `**kwargs` are the arguments to pass to the next task. They are stored as `args=list(args), kwargs=kwargs` in the chain step — same JSON format as `TaskExecution.task_args/task_kwargs`. Must be JSON-serializable.

Where `task` is a `TaskDecorator` instance or a plain function (both resolve `module_name`/`func_name` via `inspect.getmodule`). Plain functions are valid in `.then()` — they don't need `.delay()` because the chain executor creates a new `TaskExecution` for them using their `module_name`/`func_name`. Group callbacks, however, must be `TaskDecorator` instances (they are dispatched via `.delay()`).

**Decorator-time** via `on_success`:

```python
@task(on_success=task_b)
def task_a(...): ...
```

`on_success` must be a live `TaskDecorator` or plain function at import time (no forward references). It is stored on the decorator at construction. At `.delay()` time, it is resolved to `{module_name, func_name, args=[], kwargs={}}` and prepended to the chain before `_write_chain_to_db()` is called. Note: `on_success` carries no args — it only specifies which function to call next; args must be defined via `.then()` at dispatch time if needed.

Combination: `on_success` steps come first, `.then()` dispatch-time steps append after. `on_success` and `__i3group__` are orthogonal — a task can have both: it belongs to a group AND triggers a chain when it succeeds. The chain advances independently of the group counter.

### Join / Fan-out

```python
group = TaskGroup.create(
    callback=task_aggregatore,   # TaskDecorator or plain function
    total_count=len(items),      # explicit, required
    args=[],                     # passed to callback
    kwargs={}
)
for item in items:
    task_process.delay(item, __i3group__=group)
    # __i3group__ is a reserved keyword argument intercepted by TaskDecorator.delay()
    # and stripped before forwarding to the underlying function.
    # __i3group__=None (default) → standalone task, no group logic applied.
    # Using a dunder-prefixed name avoids collision with user function parameters.
```

`TaskGroup.create()` is a classmethod that saves the group immediately. `total_count` is the caller's responsibility — dispatching fewer/more children than declared leads to a group that never completes (fewer) or ignores extra completions (more, because `completed_count == total_count` fires the callback and extras hit the already-`SUCCESS` guard).

If `total_count=0`, `create()` immediately sets `status=SUCCESS` and calls `dispatch_callback()`.

The callback can head a chain:

```python
chain_handle = task_finalize.build_chain().then(task_notify)
group = TaskGroup.create(callback=chain_handle, total_count=len(items))
```

`build_chain()` is a method on `TaskDecorator` that returns a `ChainHandle(steps=[], task_execution_try=None)` without dispatching. When `.then()` is called on it, steps accumulate in memory (no DB write since no TaskExecution exists yet).

`TaskGroup.create()` accepts either a `TaskDecorator` or a `ChainHandle`:
- `TaskDecorator`: stored directly as `(callback_task_path, callback_task_name)`. `callback_chain=null`.
- `ChainHandle` with steps `[s0, s1, s2, ...]`: `s0` becomes `(callback_task_path, callback_task_name, callback_task_args, callback_task_kwargs)`. `callback_chain = [s1, s2, ...]` (the remaining steps). An empty `ChainHandle` (no `.then()` calls) is an error.

## Internal Mechanics

### ChainHandle

```python
class ChainHandle:
    task_execution_try: TaskExecutionTry | None  # None when built via build_chain()
    steps: list[dict]                             # [{module_name, func_name, args, kwargs}]

    def then(self, task, *args, **kwargs) -> ChainHandle:
        # Resolves module_name/func_name from task via inspect.getmodule.
        # Appends step to self.steps.
        # If task_execution_try is set, calls _write_chain_to_db() immediately.
        # Returns self.

    def _append_raw_step(self, step: dict):
        # Appends a pre-built {module_name, func_name, args, kwargs} dict directly.
        # Used internally by dispatch_callback(). Does NOT call _write_chain_to_db().

    def _write_chain_to_db(self):
        # UPDATE django_i3tasks_taskexecution SET chain=self.steps
        # WHERE id=task_execution_try.task_execution_id
        # Plain UPDATE, no extra transaction needed (TaskExecution already saved).
```

`.delay()` always returns a `ChainHandle` regardless of `force_sync` mode. When `force_sync=True`, `task_execution_try` is already completed, but `.then()` is still callable (it writes to DB and the chain will be picked up if the task is ever re-run). In practice, `force_sync=True` is for testing; chaining with `force_sync=True` is supported by running chain steps synchronously in sequence.

### Chaining flow

1. `task_a.delay(*args)` creates `TaskExecution` (chain=`[]`) and `TaskExecutionTry`, returns `ChainHandle(task_execution_try=try, steps=[])`.
2. At dispatch, if `on_success` is set on the decorator, it is prepended to `steps` first.
3. Each `.then()` appends to `steps` and calls `_write_chain_to_db()`.
4. The Pub/Sub message includes `task_execution_id` in `meta_info` (already existing behavior).
5. In `TaskObj._run_from_db`, after a successful run:
   - Read chain from `task_execution_try.task_execution.chain` (already loaded as FK).
   - If non-empty, pop the first step.
   - Create a new `TaskExecution` with `chain = remaining steps` and dispatch via `.delay()`.
   - If the `.delay()` call itself fails (e.g., Pub/Sub down), the exception propagates and the current task is marked failed — this aborts the chain. No silent failures.
6. On task failure (max retries exhausted): chain stops. The current `TaskExecution.chain` remains in DB but is never advanced.
7. **Retry safety**: chain continuation happens in `_run_from_db` after a successful execution. Each `TaskExecutionTry` runs independently. If try #1 fails and try #2 succeeds, the chain advances exactly once (on try #2 success). No deduplication needed.

### Join flow (atomic)

In `TaskObj._run_from_db`, after outcome is determined, if `task_execution.task_group_id` is set:

```python
should_dispatch_callback = False

with transaction.atomic():
    group = TaskGroup.objects.select_for_update().get(pk=task_execution.task_group_id)

    if group.status == TaskGroup.STATUS_FAILED:
        pass  # guard: already failed, ignore
    elif failed:
        group.failed_count += 1
        group.status = TaskGroup.STATUS_FAILED
        group.save()
    else:
        group.completed_count += 1
        if group.completed_count == group.total_count:
            group.status = TaskGroup.STATUS_SUCCESS
            group.save()
            should_dispatch_callback = True
        else:
            group.save()

if should_dispatch_callback:
    dispatch_callback(group)  # outside transaction — DB is committed before dispatch
```

If `dispatch_callback()` raises after a successful commit, the group stays `SUCCESS` in DB with no callback `TaskExecution`. Recovery is out of scope for this iteration (see Out of Scope).

### Callback dispatch

```python
def dispatch_callback(group: TaskGroup):
    module = importlib.import_module(group.callback_task_path)
    func = getattr(module, group.callback_task_name)
    # func must be a TaskDecorator (has .delay()). Plain functions are not supported
    # as group callbacks — they must be decorated with @task. This is validated in
    # TaskGroup.create() with an isinstance check.
    handle = func.delay(*group.callback_task_args, **group.callback_task_kwargs)
    if group.callback_chain:
        for step in group.callback_chain:
            # then_raw appends a pre-serialized step dict directly, skipping re-serialization
            handle._append_raw_step(step)
        handle._write_chain_to_db()
```

`_append_raw_step(step: dict)` is an internal `ChainHandle` method that pushes a pre-built `{module_name, func_name, args, kwargs}` dict directly onto `self.steps`, bypassing the `inspect.getmodule` resolution used by `.then()`. This is used only by `dispatch_callback`.

## Testing

### Unit tests (using `force_sync=True`)

- **Chaining basic**: A → B → C runs in order; `TaskExecution.chain` is correctly reduced at each step.
- **on_success + .then() combined**: `on_success` step is first; `.then()` steps follow; total chain is correct.
- **Chain stops on failure**: if B fails, C is never dispatched.
- **Chain retry safety**: B fails on try #1, succeeds on try #2 → C dispatched exactly once.
- **Chain dispatch failure**: if `.delay()` of the next step fails, current task is marked failed, chain does not silently skip.
- **Join success**: N children all succeed → callback dispatched exactly once; `group.status == SUCCESS`.
- **Join fail fast**: one child fails → `group.status == FAILED`; callback not dispatched.
- **Join already-failed guard**: a child completing after group is `FAILED` does nothing.
- **Join concurrency**: concurrent completions using threads → callback dispatched exactly once.
- **total_count=0**: `create()` immediately dispatches callback; `group.status == SUCCESS`.
- **group=None in .delay()**: task dispatched normally as standalone; no group logic applied.

### Integration tests

- End-to-end chain A → B → C via Pub/Sub emulator: verify `TaskExecution` records and `chain` field at each step.
- End-to-end fan-out of 5 tasks + aggregator: group transitions to `SUCCESS`, callback `TaskExecution` is created.

## Out of Scope

- Await/polling API (caller blocking on task result).
- Passing child results to the callback automatically — callback fetches results itself if needed.
- Modifying a chain or group after dispatch.
- Recovery from `dispatch_callback()` failures after DB commit. Known limitation: if Pub/Sub is unavailable at that moment, the group stays `SUCCESS` in DB with no callback `TaskExecution`. Detection: query `TaskGroup.objects.filter(status='success')` and check for missing callback record. Manual re-dispatch is the recovery path.
- Forward references in `on_success`.
- Dynamic `total_count` (count must be known before dispatching children).
- Passing results between chain steps — chain args are fixed at dispatch time.
