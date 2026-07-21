# django-i3tasks — Django app for managing async tasks via HTTP
# Copyright (C) 2024-2026 Ivan Bettarini
# Licensed under the GNU General Public License v3.0 or later.
# See LICENSE in the project root for full text.

import uuid

from django.conf import settings
from django.db import migrations, models
from django.db.models import Func, UUIDField
from django.utils import timezone


def _autoclean_threshold():
    """Return the configured I3TASKS.autoclean_older_than timedelta, or None."""
    i3tasks_settings = getattr(settings, 'I3TASKS', None)
    return getattr(i3tasks_settings, 'autoclean_older_than', None) if i3tasks_settings else None


def populate_uuids(apps, schema_editor):
    """Assign a DISTINCT uuid to every pre-existing row before the unique constraint.

    The preceding AddField sets ``default=uuid.uuid4``, which Django evaluates once
    for the ADD COLUMN — so every existing row is backfilled with the *same* uuid
    (not NULL). We must therefore reassign a distinct uuid to *all* rows here, or the
    following unique constraint fails on duplicates.

    Two refinements over a naive per-row loop:

    - **Optional pre-clean.** If ``I3TASKS.autoclean_older_than`` (a timedelta) is
      set, rows older than the cutoff are deleted first — fewer rows to rewrite.
    - **Backend-conditional backfill.** On PostgreSQL a single
      ``UPDATE ... SET uuid = gen_random_uuid()`` is enough: ``gen_random_uuid()`` is
      volatile and evaluated *per row* by the DB, so one statement yields a distinct
      uuid for every row (seconds, even on large tables). On other backends we fall
      back to a per-row Python loop (portable, one UPDATE per row).

    Note: a naive bulk ``.update(uuid=uuid.uuid4())`` would NOT work — ``uuid.uuid4()``
    is a single Python value evaluated once, so every row would get the same uuid.
    """
    TaskExecution = apps.get_model('i3tasks', 'TaskExecution')

    threshold = _autoclean_threshold()
    if threshold is not None:
        cutoff = timezone.now() - threshold
        TaskExecution.objects.filter(created_at__lt=cutoff).delete()

    if schema_editor.connection.vendor == 'postgresql':
        # SQL function, evaluated per row → distinct uuid for every row, one statement.
        TaskExecution.objects.update(
            uuid=Func(function='gen_random_uuid', output_field=UUIDField())
        )
    else:
        for pk in TaskExecution.objects.values_list('pk', flat=True):
            TaskExecution.objects.filter(pk=pk).update(uuid=uuid.uuid4())


class Migration(migrations.Migration):

    dependencies = [
        ('i3tasks', '0005_taskexecution_chain_taskgroup_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='taskexecution',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.RunPython(populate_uuids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='taskexecution',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
