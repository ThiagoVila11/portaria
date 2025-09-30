from django import forms
from condominio.models import Unidade
from portaria.models import Encomenda, EventoAcesso, Veiculo
from portaria.permissions import allowed_condominios_for
from condominio.models import Morador

class EncomendaForm(forms.ModelForm):
    def __init__(self, *args, user=None, is_create=False, allowed_condominios=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_create = is_create

        # --- FILTRAR CONDOMÍNIO PELOS PERMITIDOS DO USUÁRIO ---
        if user and not user.is_superuser and "condominio" in self.fields:
            # se o usuário tiver relação ManyToMany com condomínios
            if hasattr(user, "condominios_permitidos"):
                self.fields["condominio"].queryset = user.condominios_permitidos.all().order_by("nome")
            # ou, se você usar a função utilitária allowed_condominios_for:
            # self.fields["condominio"].queryset = Condominio.objects.filter(id__in=allowed_condominios_for(user))

        # --- CONDOMÍNIO → UNIDADES ---
        cond_id = (
            self.data.get("condominio") if self.data else None
        ) or getattr(self.instance, "condominio_id", None)

        if cond_id:
            self.fields["unidade"].queryset = (
                Unidade.objects.filter(bloco__condominio_id=cond_id)
                .select_related("bloco")
                .order_by("bloco__nome", "numero")
            )
        else:
            self.fields["unidade"].queryset = Unidade.objects.none()

        # --- UNIDADE → MORADORES ---
        uni_id = (
            self.data.get("unidade") if self.data else None
        ) or getattr(self.instance, "unidade_id", None)

        if uni_id:
            self.fields["destinatario"].queryset = (
                Morador.objects.filter(unidade_id=uni_id, ativo=True)
                .order_by("nome")
            )
        else:
            self.fields["destinatario"].queryset = Morador.objects.none()

        # --- ETIQUETA: deixar invisível sempre (mas aceita upload) ---
        if "etiqueta_imagem" in self.fields:
            self.fields["etiqueta_imagem"].widget = forms.ClearableFileInput(
                attrs={"style": "display:none"}
            )

        # --- STATUS: valor inicial quando é criação ---
        if is_create and "status" in self.fields:
            self.fields["status"].initial = "RECEBIDA"

    class Meta:
        model = Encomenda
        fields = [
            "condominio",
            "unidade",
            "destinatario",
            "transportadora",
            "codigo_rastreamento",
            "observacoes",
            "etiqueta_imagem",
            "status",
        ]
        widgets = {
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }



class EventoAcessoForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        # 🔹 Filtrar os condomínios permitidos para o usuário
        if user and not user.is_superuser:
            self.fields["condominio"].queryset = user.condominios_permitidos.all()

        # 🔹 Filtrar unidades pelo condomínio escolhido
        cond_id = (
            self.data.get("condominio") if self.data else None
        ) or getattr(self.instance, "condominio_id", None)

        if cond_id:
            self.fields["unidade"].queryset = (
                Unidade.objects.filter(bloco__condominio_id=cond_id)
                .select_related("bloco")
                .order_by("bloco__nome", "numero")
            )
        else:
            self.fields["unidade"].queryset = Unidade.objects.none()

    class Meta:
        model = EventoAcesso
        fields = [
            "condominio",
            "unidade",
            "pessoa_tipo",
            "pessoa_nome",
            "documento",
            #"metodo",
            "resultado",
            "motivo_negado",
        ]

class VeiculoForm(forms.ModelForm):
    class Meta:
        model = Veiculo
        fields = ["placa", "modelo", "cor", "condominio", "unidade", "proprietario"]