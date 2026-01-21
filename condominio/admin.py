from django.contrib import admin
from .models import Condominio, Bloco, Unidade, Morador
from django.http import HttpResponseRedirect
from django.urls import reverse

#admin.site.register(Condominio)
#admin.site.register(Bloco)
admin.site.register(Unidade)
#admin.site.register(Morador)

#@admin.register(Condominio)
#class CondominioAdmin(admin.ModelAdmin):
#    list_display = ("nome", "cnpj")
#    search_fields = ("nome", "cnpj")

# condominio/admin.py
@admin.register(Condominio)
class CondominioAdmin(admin.ModelAdmin):
    list_display = ("nome", "cnpj", "sf_property_id")
    search_fields = ("nome", "cnpj", "sf_property_id")
    filter_horizontal = ("usuarios",)

@admin.register(Bloco)
class BlocoAdmin(admin.ModelAdmin):
    autocomplete_fields = ("condominio",)  # precisa do search_fields acima

@admin.register(Morador)
class MoradorAdmin(admin.ModelAdmin):
    list_display = ("nome", "unidade", "ativo", "sf_contact_id", "foto", "face_id", "boleto_id")
    search_fields = ("nome", "sf_contact_id", "unidade__numero", "unidade__bloco__condominio__nome")


