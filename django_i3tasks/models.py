import uuid
from django.db import models

# Create your models here.


class CreatedUpdatedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TaskExecution(CreatedUpdatedModel):

    # APPLIED = 'APPLIED'
    # REJECTED = 'REJECTED'

    # USER_CHOICES = (
    #     (APPLIED, APPLIED),
    #     (REJECTED, REJECTED),
    # )


    # choice = models.CharField(null=False, max_length=32, blank=False, choices=USER_CHOICES)

    # id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # uuid_id = models.UUIDField(default=uuid.uuid4, editable=False)

    task_name = models.CharField(null=False, max_length=256, blank=False)
    task_path = models.CharField(null=False, max_length=256, blank=False)

    task_args = models.JSONField(null=False, blank=False, default=list)
    task_kwargs = models.JSONField(null=False, blank=False, default=dict)

    task_group = models.ForeignKey(
        'TaskGroup',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='members',
    )
    chain = models.JSONField(null=True, blank=True)
    # chain format: [{module_name, func_name, args, kwargs}, ...]

    # asked_at = models.DateTimeField(null=False, blank=True)
    # started_at = models.DateTimeField(null=False, blank=True)
    # finished_at = models.DateTimeField(null=False, blank=True)

    # reties = models.IntegerField(null=False, blank=False, default=0)
    # max_reties = models.IntegerField(null=False, blank=False, default=settings.MAX_RETRIES)


class TaskExecutionTry(CreatedUpdatedModel):
    task_execution = models.ForeignKey(
        TaskExecution,
        on_delete=models.CASCADE,
        related_name="tries",
        # blank=True,
        null=False,
    )
    try_number = models.IntegerField(null=False, blank=False, default=1)

    asked_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    is_completed = models.BooleanField(null=False, blank=False, default=False)
    is_success = models.BooleanField(null=False, blank=False, default=False)

    class Meta:
        unique_together = ['task_execution', 'try_number']
    # error = models.CharField(null=False, max_length=256, blank=False)


class TaskExecutionResult(CreatedUpdatedModel):
    task_execution_try = models.OneToOneField(
        TaskExecutionTry,
        on_delete=models.CASCADE,
        related_name="result",
        # blank=True,
        # null=False,
    )

    result = models.JSONField(null=False, blank=False, default=dict)


class TaskGroup(CreatedUpdatedModel):
    """Coordina N task paralleli verso un callback."""

    STATUS_PENDING = 'pending'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'

    callback_task_name = models.CharField(max_length=256, null=False, blank=False)
    callback_task_path = models.CharField(max_length=256, null=False, blank=False)
    callback_task_args = models.JSONField(default=list)
    callback_task_kwargs = models.JSONField(default=dict)
    # callback_chain: remaining chain steps after callback, format: [{module_name, func_name, args, kwargs}]
    callback_chain = models.JSONField(null=True, blank=True)
    # When dispatch_callback fires, TaskExecution.chain is set to callback_chain

    total_count = models.IntegerField()
    completed_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)

    status = models.CharField(max_length=16, default=STATUS_PENDING)

    class Meta:
        indexes = [models.Index(fields=['status'])]
