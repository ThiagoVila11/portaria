from django.db import models
from django.contrib.auth.models import Group
from django.conf import settings


class NivelAcesso(models.IntegerChoices):
    FUNCIONARIO = 1, 'Funcionário'
    GERENTE = 2, 'Gerente'
    ADMINISTRADOR = 3, 'Administrador'


class Perfil(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    nivel = models.IntegerField(choices=NivelAcesso.choices, default=NivelAcesso.FUNCIONARIO)


def __str__(self):
    return f"Perfil de {self.user.get_username()} (nível {self.get_nivel_display()})"