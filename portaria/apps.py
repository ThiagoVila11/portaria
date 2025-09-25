#from django.apps import AppConfig

#class PortariaConfig(AppConfig):
#    default_auto_field = "django.db.models.BigAutoField"
#    name = "portaria"

#    def ready(self):
#        import portaria.signals  # noqa

from django.apps import AppConfig
from django.db.utils import OperationalError, ProgrammingError


class PortariaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'portaria'

    def ready(self):
        """
        Carrega os signals apenas quando o banco já estiver utilizável.
        Evita erro em `python manage.py migrate` inicial.
        """
        try:
            import portaria.signals  # noqa
        except (OperationalError, ProgrammingError):
            # Evita quebrar durante migrações iniciais
            pass
