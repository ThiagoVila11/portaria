# portaria/forms.py
from django import forms
from condominio.models import Unidade
from portaria.models import Encomenda
from portaria.permissions import allowed_condominios_for

class EncomendaForm(forms.ModelForm):
    class Meta:
        model = Encomenda
        fields = [
            "condominio", "unidade", "destinatario",
            "transportadora", "codigo_rastreamento",
            "observacoes", "etiqueta_imagem", "status",
        ]

    def __init__(self, *args, user=None, is_create=False, **kwargs):
        super().__init__(*args, **kwargs)

        # --- (seu filtro por condomínio) ---
        allowed = allowed_condominios_for(user).order_by("nome") if user else self.fields["condominio"].queryset.none()
        self.fields["condominio"].queryset = allowed

        cond_id = (self.data.get("condominio") if self.data else None) or getattr(self.instance, "condominio_id", None)
        if cond_id:
            self.fields["unidade"].queryset = Unidade.objects.filter(
                bloco__condominio_id=cond_id
            ).select_related("bloco", "bloco__condominio").order_by("bloco__nome", "numero")
        else:
            self.fields["unidade"].queryset = Unidade.objects.filter(
                bloco__condominio__in=allowed
            ).select_related("bloco", "bloco__condominio").order_by("bloco__nome", "numero")

        # --- comportamento de inclusão ---
        if is_create:
            # some com a etiqueta do form (não renderiza)
            self.fields.pop("etiqueta_imagem", None)
            # mantém 'status' como campo oculto com valor RECEBIDA
            if "status" in self.fields:
                self.fields["status"].initial = "RECEBIDA"
                self.fields["status"].widget = forms.HiddenInput()
