import uuid
from django.db import models

# Create your models here.


class CreatedUpdatedModel(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

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

    task_name = models.CharField(null=False, max_length=256, blank=False)
    task_path = models.CharField(null=False, max_length=256, blank=False)

    task_args = models.JSONField(null=False, blank=False, default=list)
    task_kwargs = models.CharField(null=False, blank=False, default=dict)

    asked_at = models.DateTimeField(null=False, blank=True)
    started_at = models.DateTimeField(null=False, blank=True)
    finished_at = models.DateTimeField(null=False, blank=True)
