from django.apps import AppConfig


class GammeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'Gamme'
def ready(self):
    import Gamme.signals 