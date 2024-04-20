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
