import inspect
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
