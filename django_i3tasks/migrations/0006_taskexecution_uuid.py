# django-i3tasks — Django app for managing async tasks via HTTP
# Copyright (C) 2024-2026 Ivan Bettarini
# Licensed under the GNU General Public License v3.0 or later.
# See LICENSE in the project root for full text.

import uuid

from django.db import migrations, models


def populate_uuids(apps, schema_editor):
    """Assign a fresh uuid to every pre-existing row before the unique constraint.

    The preceding AddField sets ``default=uuid.uuid4``, which Django evaluates once
    for the ADD COLUMN — so every existing row is backfilled with the *same* uuid
    (not NULL). We must therefore reassign a distinct uuid to *all* rows here,
    unconditionally, or the following unique constraint fails on duplicates.
    """
    TaskExecution = apps.get_model('i3tasks', 'TaskExecution')
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
