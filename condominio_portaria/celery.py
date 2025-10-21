import os
from celery import Celery

# 🔹 Corrija aqui para apontar para o módulo certo
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "condominio_portaria.settings")

app = Celery("condominio_portaria")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
