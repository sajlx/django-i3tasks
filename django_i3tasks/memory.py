# django-i3tasks — Django app for managing async tasks via HTTP
# Copyright (C) 2024-2026 Ivan Bettarini
# Licensed under the GNU General Public License v3.0 or later.
# See LICENSE in the project root for full text.

"""
Opt-in memory log of task executions (``I3TASKS.memory_log = True``).

Each run logs one line with the resident memory (RSS) of the *process* at the
start and end of the task, the peak sampled while it ran, and which other tasks
were running in the same process at the same time::

    i3tasks_memory func=check_and_update_fiscal_events id=12 status=ok
    start_mb=312.4 end_mb=388.0 peak_mb=641.2 delta_mb=75.6
    in_flight_max=3 in_flight=check_pending_invoices,check_aruba_invoice_status

The numbers are per process, not per task: with several tasks (or requests)
sharing a Cloud Run instance the peak is the sum of what ran together, which is
why the other running tasks are listed. Use it to find which task, or which
combination, drives an out-of-memory kill; it does not attribute bytes to a task.

Reads ``/proc/self/statm`` (Linux). Where it is missing the values are ``None``
and the line is still logged, without numbers. No extra dependency.
"""

import logging
import os
import threading
import time
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_running = {}  # token -> func_name, for the tasks running now in this process
_token_counter = 0

try:
    _PAGE_SIZE = os.sysconf('SC_PAGE_SIZE')
except (AttributeError, ValueError, OSError):  # pragma: no cover - non-POSIX
    _PAGE_SIZE = 4096


def read_rss_mb():
    """Resident set size of this process in MB, None where it cannot be read."""
    try:
        with open('/proc/self/statm') as f:
            return int(f.read().split()[1]) * _PAGE_SIZE / (1024 * 1024)
    except (OSError, ValueError, IndexError):
        return None


def _fmt(value):
    return 'n/a' if value is None else f'{value:.1f}'


class _Sampler(threading.Thread):
    """Samples RSS every `interval` seconds and keeps the peak and the in-flight set."""

    def __init__(self, interval, peak_mb, in_flight_max, in_flight_seen):
        super().__init__(daemon=True, name='i3tasks-memory-sampler')
        self.interval = interval
        self.peak_mb = peak_mb
        self.in_flight_max = in_flight_max
        self.in_flight_seen = in_flight_seen
        self._stop_event = threading.Event()

    def sample(self):
        rss = read_rss_mb()
        if rss is not None and (self.peak_mb is None or rss > self.peak_mb):
            self.peak_mb = rss
        with _lock:
            names = list(_running.values())
        self.in_flight_max = max(self.in_flight_max, len(names))
        self.in_flight_seen.update(names)

    def run(self):
        while not self._stop_event.wait(self.interval):
            self.sample()

    def stop(self):
        self._stop_event.set()


@contextmanager
def track_memory(func_name, execution_id=None, interval_ms=200):
    """Log the memory line for the task run inside the ``with`` block.

    Never raises on its own and never swallows the task's exception.
    """
    global _token_counter
    with _lock:
        _token_counter += 1
        token = _token_counter
        _running[token] = func_name

    start_mb = read_rss_mb()
    sampler = _Sampler(max(interval_ms, 10) / 1000.0, start_mb, 1, set())
    status = 'error'
    try:
        sampler.sample()
        sampler.start()
        yield
        status = 'ok'
    finally:
        sampler.stop()
        sampler.sample()  # catches a peak that ended before the next tick
        end_mb = read_rss_mb()
        with _lock:
            _running.pop(token, None)
        others = sorted(sampler.in_flight_seen - {func_name})
        delta = None if start_mb is None or end_mb is None else end_mb - start_mb
        logger.info(
            "i3tasks_memory func=%s id=%s status=%s start_mb=%s end_mb=%s peak_mb=%s delta_mb=%s "
            "in_flight_max=%s in_flight=%s",
            func_name, execution_id if execution_id is not None else '-', status,
            _fmt(start_mb), _fmt(end_mb), _fmt(sampler.peak_mb), _fmt(delta),
            sampler.in_flight_max, ','.join(others) or '-',
        )
