from django.apps import AppConfig


class I3TasksConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    label = 'i3tasks'
    name = 'django_i3tasks'

    def ready(self):
        from django.conf import settings # NoQA

        if not hasattr(settings, 'I3TASKS'):
            raise AttributeError("I3TASKS settings not found")
        if not hasattr(settings, 'PUBSUB_CONFIG'):
            raise AttributeError("PUBSUB_CONFIG settings not found")

        i3tasks_settings = getattr(settings, 'I3TASKS', {})

        if i3tasks_settings.run_queue_create_command_on_startup:

            from django.core.management import call_command  # NoQA

            call_command("i3tasks_ensure_pubsub")
