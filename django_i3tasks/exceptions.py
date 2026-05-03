# django-i3tasks — Django app for managing async tasks via HTTP
# Copyright (C) 2024-2026 Ivan Bettarini
# Licensed under the GNU General Public License v3.0 or later.
# See LICENSE in the project root for full text.


class MaxRetriesExceededError(Exception):
    def __init__(self, message):
        super().__init__(message)