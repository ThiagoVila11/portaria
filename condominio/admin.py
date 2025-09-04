from django.contrib import admin
from .models import Condominio, Bloco, Unidade, Morador


#admin.site.register(Condominio)
#admin.site.register(Bloco)
admin.site.register(Unidade)
admin.site.register(Morador)


@admin.register(Condominio)
class CondominioAdmin(admin.ModelAdmin):
    list_display = ("nome", "cnpj")
    search_fields = ("nome", "cnpj")

@admin.register(Bloco)
class BlocoAdmin(admin.ModelAdmin):
    autocomplete_fields = ("condominio",)  # precisa do search_fields acima
