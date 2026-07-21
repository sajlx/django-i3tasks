# django-i3tasks — Django app for managing async tasks via HTTP
# Copyright (C) 2024-2026 Ivan Bettarini
# Licensed under the GNU General Public License v3.0 or later.
# See LICENSE in the project root for full text.

from datetime import timedelta
from logging import getLogger

from django.core.management.base import BaseCommand, CommandError

from django_i3tasks.maintenance import (
    _configured_threshold,
    clean_old_task_executions,
    old_task_executions,
)

logger = getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Delete TaskExecution records (and their cascaded tries/results) older than "
        "I3TASKS.autoclean_older_than, or --days N to override. Schedule it (cron / "
        "Cloud Scheduler / a beat schedule) to keep the task tables from growing "
        "unbounded."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            dest='days',
            type=float,
            default=None,
            help='Override the retention window: delete rows older than N days.',
        )
        parser.add_argument(
            '--batch-size',
            dest='batch_size',
            type=int,
            default=None,
            help='Delete in chunks of N rows (one transaction each) instead of a '
                 'single large DELETE. Recommended for the first purge of a big table.',
        )
        parser.add_argument(
            '--dry-run',
            dest='dry_run',
            action='store_true',
            default=False,
            help='Report how many rows would be deleted without deleting anything.',
        )

    def handle(self, *args, **options):
        days = options.get('days')
        older_than = timedelta(days=days) if days is not None else None

        if older_than is None and _configured_threshold() is None:
            raise CommandError(
                "No retention window: set I3TASKS.autoclean_older_than or pass --days N."
            )

        if options.get('dry_run'):
            qs = old_task_executions(older_than)
            count = qs.count() if qs is not None else 0
            self.stdout.write(f"[dry-run] {count} TaskExecution rows would be deleted.")
            return

        deleted = clean_old_task_executions(older_than, batch_size=options.get('batch_size'))
        logger.info("i3tasks_clean deleted %s TaskExecution rows", deleted)
        self.stdout.write(f"Deleted {deleted} TaskExecution rows.")
