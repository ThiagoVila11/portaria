from django.contrib import admin
from .models import Encomenda, EventoAcesso, Parametro, Veiculo




@admin.register(Encomenda)
class EncomendaAdmin(admin.ModelAdmin):
    list_display = ("id", "condominio", "unidade", "destinatario", "status", "data_recebimento", "data_entrega")
    list_filter = ("condominio", "status")
    search_fields = ("codigo_rastreamento", "destinatario__nome")


@admin.register(EventoAcesso)
class EventoAcessoAdmin(admin.ModelAdmin):
    list_display = ("id", "condominio", "pessoa_nome", "pessoa_tipo", "resultado", "criado_em")
    list_filter = ("condominio", "resultado", "pessoa_tipo")
    search_fields = ("pessoa_nome", "documento")

@admin.register(Parametro)
class ParametroAdmin(admin.ModelAdmin):
    list_display = ("id", "ParametroNome", "ParametroValor")
    list_filter = ("ParametroNome", "ParametroValor")
    search_fields = ("ParametroNome", "ParametroValor")

@admin.register(Veiculo)
class VeiculoAdmin(admin.ModelAdmin):
    list_display = ("id", "placa", "modelo", "cor")
    list_filter = ("placa", "modelo", "cor")
    search_fields = ("placa", "modelo", "cor")