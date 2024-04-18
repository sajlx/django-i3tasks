from django.contrib import admin

from .models import TaskExecution
from .models import TaskExecutionResult
from .models import TaskExecutionTry


@admin.register(TaskExecution)
class TaskExecutionAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "task_name",
        "task_path",
        "created_at",
        # "started_at",
        # "finished_at",
    ]


@admin.register(TaskExecutionTry)
class TaskExecutionTryAdmin(admin.ModelAdmin):
    list_display = [
        "get_task_id",
        "get_task_name",
        "get_task_path",
        # "asked_at",
        # "started_at",
        # "finished_at",
        'try_number',
        'asked_at',
        'started_at',
        'finished_at',
        'is_completed',
        'is_success'
    ]

    list_filter = [
        'is_completed',
        'is_success',
    ]

    @admin.display(ordering='task_execution__id', description='Task Execution ID')
    def get_task_id(self, obj):
        return obj.task_execution.id

    @admin.display(ordering='task_execution__task_name', description='Task Name')
    def get_task_name(self, obj):
        return obj.task_execution.task_name

    @admin.display(ordering='task_execution__task_path', description='Task Path')
    def get_task_path(self, obj):
        return obj.task_execution.task_path


@admin.register(TaskExecutionResult)
class TaskExecutionResultAdmin(admin.ModelAdmin):
    list_display = [
        "get_task_id",
        "get_task_name",
        "get_task_path",
        # "asked_at",
        # "started_at",
        # "finished_at",
    ]

    @admin.display(ordering='task_execution_try__task_execution__id', description='Task Execution ID')
    def get_task_id(self, obj):
        return obj.task_execution_try.task_execution.id

    @admin.display(ordering='task_execution_try__task_execution__task_name', description='Task Name')
    def get_task_name(self, obj):
        return obj.task_execution_try.task_execution.task_name

    @admin.display(ordering='task_execution_try__task_execution__task_path', description='Task Path')
    def get_task_path(self, obj):
        return obj.task_execution_try.task_execution.task_path