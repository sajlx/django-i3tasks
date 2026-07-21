# django-i3tasks — Django app for managing async tasks via HTTP
# Copyright (C) 2024-2026 Ivan Bettarini
# Licensed under the GNU General Public License v3.0 or later.
# See LICENSE in the project root for full text.

"""Housekeeping helpers for old task-execution records.

The retention window comes from ``I3TASKS.autoclean_older_than`` (a ``timedelta``)
unless an explicit ``older_than`` is passed. Deleting a ``TaskExecution`` cascades
to its ``TaskExecutionTry`` rows and their ``TaskExecutionResult`` (FK on_delete=CASCADE).
"""

from django.conf import settings
from django.utils import timezone

from .models import TaskExecution


def _configured_threshold():
    """Return I3TASKS.autoclean_older_than (a timedelta) or None if unset."""
    i3tasks_settings = getattr(settings, 'I3TASKS', None)
    return getattr(i3tasks_settings, 'autoclean_older_than', None) if i3tasks_settings else None


def old_task_executions(older_than=None):
    """QuerySet of TaskExecution older than the cutoff, or None if no threshold.

    older_than: a timedelta. Falls back to I3TASKS.autoclean_older_than.
    """
    if older_than is None:
        older_than = _configured_threshold()
    if older_than is None:
        return None
    cutoff = timezone.now() - older_than
    return TaskExecution.objects.filter(created_at__lt=cutoff)


def clean_old_task_executions(older_than=None, batch_size=None):
    """Delete TaskExecution rows older than the cutoff (cascades to tries/results).

    older_than: a timedelta. Falls back to I3TASKS.autoclean_older_than.
    batch_size: if given, delete in chunks of this many rows (one transaction per
        chunk) instead of a single large DELETE — safer for a big first purge.

    Returns the number of TaskExecution rows deleted. No-op returning 0 when no
    threshold is configured/passed.
    """
    qs = old_task_executions(older_than)
    if qs is None:
        return 0

    if not batch_size:
        count = qs.count()
        qs.delete()
        return count

    total = 0
    while True:
        pks = list(qs.values_list('pk', flat=True)[:batch_size])
        if not pks:
            break
        TaskExecution.objects.filter(pk__in=pks).delete()
        total += len(pks)
    return total
