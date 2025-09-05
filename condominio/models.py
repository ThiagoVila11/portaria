# condominio/models.py
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class Condominio(models.Model):
    nome = models.CharField(max_length=120)
    cnpj = models.CharField(max_length=18, blank=True)
    # NOVO: usuários que podem acessar este condomínio
    usuarios = models.ManyToManyField(
        User,
        blank=True,
        related_name="condominios_permitidos",
    )
    sf_property_id = models.CharField("Salesforce Property Id", max_length=18, blank=True)

    def __str__(self):
        return self.nome


class Bloco(models.Model):
    condominio = models.ForeignKey(Condominio, on_delete=models.CASCADE, related_name="blocos")
    nome = models.CharField(max_length=60)

    def __str__(self):
        return f"{self.condominio} - Bloco {self.nome}"
 


class Unidade(models.Model):
    bloco = models.ForeignKey(Bloco, on_delete=models.CASCADE, related_name="unidades")
    numero = models.CharField(max_length=20)
    andar = models.CharField(max_length=10, blank=True)

    class Meta:
        unique_together = ("bloco", "numero")

    def __str__(self):
        return f"{self.bloco} - Unidade {self.numero}"


class Morador(models.Model):
    nome = models.CharField(max_length=120)
    documento = models.CharField(max_length=20, blank=True)  # CPF/RG
    unidade = models.ForeignKey(Unidade, on_delete=models.PROTECT, related_name="moradores")
    ativo = models.BooleanField(default=True)
    sf_contact_id = models.CharField("Salesforce Contact Id", max_length=18, blank=True)

    def __str__(self):
        return f"{self.nome} ({self.unidade})"
