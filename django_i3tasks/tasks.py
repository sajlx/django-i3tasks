# django-i3tasks — Django app for managing async tasks via HTTP
# Copyright (C) 2024-2026 Ivan Bettarini
# Licensed under the GNU General Public License v3.0 or later.
# See LICENSE in the project root for full text.

import logging

from .utils import TaskDecorator


logger = logging.getLogger(__name__)


@TaskDecorator
def test_task(*args, **kwargs):
    mex = f"This is the test task with args: {args} and kwargs: {kwargs}"
    logger.info(mex)
    return mex
