from django.contrib import admin
from .models import Condominio, Bloco, Unidade, Morador


admin.site.register(Condominio)
admin.site.register(Bloco)
admin.site.register(Unidade)
admin.site.register(Morador)
