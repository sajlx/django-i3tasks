from django.contrib import admin

from .models import TaskExecution


@admin.register(TaskExecution)
class TaskExecutionAdmin(admin.ModelAdmin):
    list_display = [
        "task_name",
        "task_path",
        "asked_at",
        "started_at",
        "finished_at",
    ]
