from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        # Import signals supaya handler invalidasi cache teregister
        from . import signals  # noqa: F401
