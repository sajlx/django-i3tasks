# django-i3tasks — Django app for managing async tasks via HTTP
# Copyright (C) 2024-2026 Ivan Bettarini
# Licensed under the GNU General Public License v3.0 or later.
# See LICENSE in the project root for full text.

# django_i3tasks/tests_tasks.py
import logging
from .utils import TaskDecorator

logger = logging.getLogger(__name__)

results = []  # lista globale per verificare l'ordine di esecuzione nei test


@TaskDecorator
def task_a(*args, **kwargs):
    results.append('a')
    return 'result_a'


@TaskDecorator
def task_b(*args, **kwargs):
    results.append('b')
    return 'result_b'


@TaskDecorator
def task_c(*args, **kwargs):
    results.append('c')
    return 'result_c'


@TaskDecorator
def task_fail(*args, **kwargs):
    raise ValueError("task intenzionalmente fallito")


@TaskDecorator
def task_aggregator(*args, **kwargs):
    results.append('aggregator')
    return 'result_aggregator'


@TaskDecorator(on_success=task_b)
def my_task(*args, **kwargs):
    return 'ok'


@TaskDecorator(on_success=task_b)
def my_task2(*args, **kwargs):
    return 'ok'
