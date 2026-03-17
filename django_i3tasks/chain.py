import inspect
import importlib
import logging

logger = logging.getLogger(__name__)


class ChainHandle:
    """
    Handle restituito da TaskDecorator.delay(). Permette di concatenare task
    con .then() e coordina il join tramite TaskGroup.
    """

    def __init__(self, task_execution_try, steps=None):
        self.task_execution_try = task_execution_try  # None se build_chain()
        self.steps = steps if steps is not None else []
        # Tracks the most-recently dispatched tail handle in force_sync mode
        self._tail_handle = None

    def then(self, task, *args, **kwargs):
        """
        Aggiunge un passo alla catena.
        task: TaskDecorator o funzione plain (deve avere __name__ e module).
        *args, **kwargs: argomenti da passare al prossimo task.
        """
        func = getattr(task, '_func', task)  # TaskDecorator wraps _func
        module_name = inspect.getmodule(func).__name__
        func_name = func.__name__
        step = {
            'module_name': module_name,
            'func_name': func_name,
            'args': list(args),
            'kwargs': kwargs,
        }
        self.steps.append(step)
        if self.task_execution_try is not None:
            self._write_chain_to_db()
            # If the previous task already completed successfully (force_sync mode),
            # execute the next step immediately using the tail handle.
            tail = self._tail_handle if self._tail_handle is not None else self
            tail_try = tail.task_execution_try
            if tail_try is not None and tail_try.is_completed and tail_try.is_success:
                try:
                    next_module = importlib.import_module(step['module_name'])
                    next_func = getattr(next_module, step['func_name'])
                    next_args = step.get('args', [])
                    next_kwargs = step.get('kwargs', {})
                    next_handle = next_func.delay(*next_args, **next_kwargs)
                    self._tail_handle = next_handle
                except Exception as chain_exc:
                    logger.error(f"Chain continuation failed: {chain_exc}", exc_info=True)
                    raise
        return self

    def _append_raw_step(self, step: dict):
        """
        Aggiunge un passo pre-serializzato senza DB write.
        Usato internamente da dispatch_callback().
        """
        self.steps.append(step)

    def _write_chain_to_db(self):
        """
        Aggiorna TaskExecution.chain nel DB con i passi correnti.
        """
        from .models import TaskExecution
        TaskExecution.objects.filter(
            id=self.task_execution_try.task_execution_id
        ).update(chain=self.steps)


def dispatch_callback(group):
    """
    Dispatches the callback task stored in the group.
    Called when all group members have completed successfully.
    group: TaskGroup instance with status SUCCESS.
    """
    try:
        module = importlib.import_module(group.callback_task_path)
        func = getattr(module, group.callback_task_name)
        handle = func.delay(*group.callback_task_args, **group.callback_task_kwargs)
        if group.callback_chain:
            for step in group.callback_chain:
                handle._append_raw_step(step)
            handle._write_chain_to_db()
    except Exception as exc:
        logger.error(
            f"dispatch_callback failed for TaskGroup pk={group.pk}: {exc}",
            exc_info=True,
        )
        raise
