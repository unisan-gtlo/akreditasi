from django.apps import AppConfig


class MasterAkreditasiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'master_akreditasi'
    verbose_name = 'Master Akreditasi'

    def ready(self):
        # Import signals supaya handler @receiver teregister
        from . import signals  # noqa: F401