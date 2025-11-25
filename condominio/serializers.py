from rest_framework import serializers
from condominio.models import Bloco

class BlocoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bloco
        fields = ['id', 'condominio', 'nome', 'usuarios_permitidos']
        