# django-i3tasks — Django app for managing async tasks via HTTP
# Copyright (C) 2024-2026 Ivan Bettarini
# Licensed under the GNU General Public License v3.0 or later.
# See LICENSE in the project root for full text.

import logging
from datetime import timedelta

from .utils import TaskDecorator
from .maintenance import clean_old_task_executions


logger = logging.getLogger(__name__)


@TaskDecorator
def test_task(*args, **kwargs):
    mex = f"This is the test task with args: {args} and kwargs: {kwargs}"
    logger.info(mex)
    return mex


@TaskDecorator
def autoclean_task(days=None, batch_size=None):
    """Built-in task: prune TaskExecution rows older than the retention window.

    Runs inside i3tasks itself, so you can schedule it via I3TASKS.schedules
    instead of (or in addition to) the `i3tasks_clean` command / an external cron:

        Schedule(module_name='django_i3tasks.tasks', func_name='autoclean_task',
                 cron='0 3 * * *', args=[], kwargs={})            # window from settings
        Schedule(..., kwargs={'days': 30})                        # explicit override
        Schedule(..., kwargs={'days': 30, 'batch_size': 5000})   # chunked delete

    ``days`` overrides ``I3TASKS.autoclean_older_than``; with neither set it is a
    no-op. ``batch_size`` deletes in chunks instead of one large DELETE. Returns
    ``{"deleted": <n>}``.
    """
    older_than = timedelta(days=days) if days is not None else None
    deleted = clean_old_task_executions(older_than, batch_size=batch_size)
    logger.info("autoclean_task deleted %s TaskExecution rows", deleted)
    return {"deleted": deleted}
