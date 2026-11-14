from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        # Importing the module registers the notification signal receivers.
        from . import notifications  # noqa: F401
