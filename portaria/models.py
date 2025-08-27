import uuid
from django.db import models
from django.contrib.auth import get_user_model
from condominio.models import Condominio, Unidade, Morador


User = get_user_model()

class StatusEncomenda(models.TextChoices):
    RECEBIDA = 'RECEBIDA', 'Recebida'
    ENTREGUE = 'ENTREGUE', 'Entregue ao Morador'
    DEVOLVIDA = 'DEVOLVIDA', 'Devolvida ao Remetente'


class Encomenda(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    condominio = models.ForeignKey(Condominio, on_delete=models.PROTECT)
    unidade = models.ForeignKey(Unidade, on_delete=models.PROTECT)
    destinatario = models.ForeignKey(Morador, on_delete=models.PROTECT)
    transportadora = models.CharField(max_length=120, blank=True)
    codigo_rastreamento = models.CharField(max_length=80, blank=True)
    recebido_por = models.ForeignKey(User, on_delete=models.PROTECT, related_name='encomendas_recebidas')
    status = models.CharField(max_length=12, choices=StatusEncomenda.choices, default=StatusEncomenda.RECEBIDA)
    data_recebimento = models.DateTimeField(auto_now_add=True)
    data_entrega = models.DateTimeField(null=True, blank=True)
    entregue_por = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name='encomendas_entregues')
    foto = models.ImageField(upload_to='encomendas/fotos/', blank=True)
    assinatura_entrega = models.ImageField(upload_to='encomendas/assinaturas/', blank=True)
    observacoes = models.TextField(blank=True)


    class Meta:
        permissions = [
            ("pode_entregar_encomenda", "Pode entregar/baixar encomenda"),
            ("pode_receber_encomenda", "Pode receber/registrar chegada de encomenda"),
        ]


def __str__(self):
    return f"Encomenda {self.id} - {self.destinatario} - {self.get_status_display()}"


class TipoPessoa(models.TextChoices):
    MORADOR = 'MORADOR', 'Morador'
    VISITANTE = 'VISITANTE', 'Visitante'
    PRESTADOR = 'PRESTADOR', 'Prestador'
    ENTREGADOR = 'ENTREGADOR', 'Entregador'


class MetodoAcesso(models.TextChoices):
    TAG = 'TAG', 'TAG/Cartão'
    QR = 'QR', 'QR Code'
    BIOMETRIA = 'BIO', 'Biometria'
    SENHA = 'PWD', 'Senha'


class ResultadoAcesso(models.TextChoices):
    PERMITIDO = 'OK', 'Permitido'
    NEGADO = 'NO', 'Negado'


class EventoAcesso(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    condominio = models.ForeignKey(Condominio, on_delete=models.PROTECT)
    unidade = models.ForeignKey(Unidade, on_delete=models.PROTECT, null=True, blank=True)
    pessoa_tipo = models.CharField(max_length=12, choices=TipoPessoa.choices)
    pessoa_nome = models.CharField(max_length=120)
    documento = models.CharField(max_length=20, blank=True)
    metodo = models.CharField(max_length=3, choices=MetodoAcesso.choices)
    resultado = models.CharField(max_length=2, choices=ResultadoAcesso.choices)
    motivo_negado = models.CharField(max_length=200, blank=True)
    criado_por = models.ForeignKey(User, on_delete=models.PROTECT)
    criado_em = models.DateTimeField(auto_now_add=True)


class Meta:
    permissions = [
    ("pode_registrar_acesso", "Pode registrar evento de acesso"),
    ]


def __str__(self):
    return f"Acesso {self.pessoa_nome} - {self.get_resultado_display()} ({self.criado_em:%d/%m %H:%M})"