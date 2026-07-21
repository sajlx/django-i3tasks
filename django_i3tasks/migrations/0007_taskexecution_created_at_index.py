# django-i3tasks — Django app for managing async tasks via HTTP
# Copyright (C) 2024-2026 Ivan Bettarini
# Licensed under the GNU General Public License v3.0 or later.
# See LICENSE in the project root for full text.

from django.db import migrations, models

INDEX_NAME = 'i3tasks_te_created_idx'


def _quote(schema_editor, identifier):
    return schema_editor.connection.ops.quote_name(identifier)


def create_index(apps, schema_editor):
    """Create the created_at index — CONCURRENTLY on PostgreSQL (no write lock).

    Requires the migration to run outside a transaction (``atomic = False``),
    since CREATE INDEX CONCURRENTLY cannot run inside one. Other backends get a
    plain CREATE INDEX (cheap; SQLite/tests).
    """
    model = apps.get_model('i3tasks', 'TaskExecution')
    table = _quote(schema_editor, model._meta.db_table)
    column = _quote(schema_editor, model._meta.get_field('created_at').column)
    concurrently = 'CONCURRENTLY ' if schema_editor.connection.vendor == 'postgresql' else ''
    schema_editor.execute(
        f'CREATE INDEX {concurrently}IF NOT EXISTS "{INDEX_NAME}" ON {table} ({column})'
    )


def drop_index(apps, schema_editor):
    concurrently = 'CONCURRENTLY ' if schema_editor.connection.vendor == 'postgresql' else ''
    schema_editor.execute(f'DROP INDEX {concurrently}IF EXISTS "{INDEX_NAME}"')


class Migration(migrations.Migration):
    # CREATE INDEX CONCURRENTLY must not run inside a transaction.
    atomic = False

    dependencies = [
        ('i3tasks', '0006_taskexecution_uuid'),
    ]

    operations = [
        # State knows about the index (keeps makemigrations quiet); the DB side
        # is a vendor-conditional raw statement so PostgreSQL can go CONCURRENTLY.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddIndex(
                    model_name='taskexecution',
                    index=models.Index(fields=['created_at'], name=INDEX_NAME),
                ),
            ],
            database_operations=[
                migrations.RunPython(create_index, drop_index),
            ],
        ),
    ]
