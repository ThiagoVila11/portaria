from django import forms
from condominio.models import Unidade, Condominio, Morador, Bicicleta, Bloco
from portaria.models import Encomenda, EventoAcesso, Veiculo
from portaria.permissions import allowed_condominios_for

class EncomendaForm(forms.ModelForm):
    def __init__(self, *args, user=None, is_create=False, allowed_condominios=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_create = is_create

        # --- FILTRAR CONDOMÍNIO PELOS PERMITIDOS DO USUÁRIO ---
        if "condominio" in self.fields:
            if user and not user.is_superuser and hasattr(user, "condominios_permitidos"):
                qs = user.condominios_permitidos.all().order_by("nome")
                self.fields["condominio"].queryset = qs

                # ✅ Se só houver 1 condomínio, já define como valor inicial e remove a opção em branco
                if qs.count() == 1:
                    self.fields["condominio"].initial = qs.first()
                    self.fields["condominio"].empty_label = None
            else:
                # superuser ou sem restrição → todos os condomínios
                self.fields["condominio"].queryset = Condominio.objects.all().order_by("nome")

        # --- CONDOMÍNIO → UNIDADES ---
        cond_id = (
            self.data.get("condominio") if self.data else None
        ) or getattr(self.instance, "condominio_id", None) or (
            self.fields["condominio"].initial.id if self.fields["condominio"].initial else None
        )

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

        # --- ETIQUETA invisível ---
        if "etiqueta_imagem" in self.fields:
            self.fields["etiqueta_imagem"].widget = forms.ClearableFileInput(
                attrs={"style": "display:none"}
            )

        # --- STATUS inicial ---
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
            "PackageName",
            "etiqueta_imagem",
            "status",
            "arquivo_01",
            "arquivo_02",
            "arquivo_03",
            "arquivo_04",
            "arquivo_05",
        ]
        widgets = {
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }


class EventoAcessoForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        # 🔹 Torna todos os campos obrigatórios
        for field in self.fields.values():
            field.required = True

        # 🔹 Remove opções "Negado" e "Liberado" apenas na criação
        #if not self.instance.pk:
        escolhas = self.fields["resultado"].choices
        self.fields["resultado"].choices = [
                (valor, label  )
                for valor, label in escolhas
                if valor not in ["Cancelled", "Checked In"]
            ]


        # 🔹 Filtra condomínios permitidos
        if user and not user.is_superuser:
            self.fields["condominio"].queryset = user.condominios_permitidos.all()

        # 🔹 Condomínio escolhido
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

        # 🔹 Unidade escolhida
        uni_id = (
            self.data.get("unidade") if self.data else None
        ) or getattr(self.instance, "unidade_id", None)

        if uni_id:
            self.fields["responsavel"].queryset = (
                Morador.objects.filter(unidade_id=uni_id).order_by("nome")
            )
        else:
            self.fields["responsavel"].queryset = Morador.objects.none()

    class Meta:
        model = EventoAcesso
        fields = [
            "condominio",
            "unidade",
            "responsavel",
            "pessoa_tipo",
            "pessoa_nome",
            "pessoa_telefone",
            "resultado",
            #"motivo_negado",
        ]

class VeiculoForm(forms.ModelForm):
    class Meta:
        model = Veiculo
        fields = ["placa", "modelo", "cor", "condominio", "unidade", "proprietario"]

class BicicletaForm(forms.ModelForm):
    condominio = forms.ModelChoiceField(
        queryset=Condominio.objects.none(),
        label="Condomínio",
        required=True,
        widget=forms.Select(attrs={"class": "form-select"})
    )
    bloco = forms.ModelChoiceField(
        queryset=Bloco.objects.none(),
        label="Bloco",
        required=True,
        widget=forms.Select(attrs={"class": "form-select"})
    )
    unidade = forms.ModelChoiceField(
        queryset=Unidade.objects.none(),
        label="Unidade",
        required=True,
        widget=forms.Select(attrs={"class": "form-select"})
    )

    class Meta:
        model = Bicicleta
        fields = ["condominio", "bloco", "unidade", "modelo"]
        widgets = {
            "modelo": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex: Caloi, Trek, Oggi..."}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # 🔹 Condominios — todos se admin, apenas os do usuário comum
        if user and (user.is_staff or user.is_superuser):
            self.fields["condominio"].queryset = Condominio.objects.all().order_by("nome")
        elif user:
            self.fields["condominio"].queryset = Condominio.objects.filter(usuarios=user).order_by("nome")
        else:
            self.fields["condominio"].queryset = Condominio.objects.none()

        # 🔹 Se veio condominio no POST
        if "condominio" in self.data:
            try:
                cond_id = int(self.data.get("condominio"))
                self.fields["bloco"].queryset = Bloco.objects.filter(condominio_id=cond_id).order_by("nome")
            except (ValueError, TypeError):
                pass
        elif self.instance.pk:
            # Edição — já tem instância
            self.fields["bloco"].queryset = Bloco.objects.filter(condominio=self.instance.bloco.condominio)

        # 🔹 Se veio bloco no POST
        if "bloco" in self.data:
            try:
                bloco_id = int(self.data.get("bloco"))
                self.fields["unidade"].queryset = Unidade.objects.filter(bloco_id=bloco_id).order_by("numero")
            except (ValueError, TypeError):
                pass
        elif self.instance.pk:
            # Edição
            self.fields["unidade"].queryset = Unidade.objects.filter(bloco=self.instance.bloco)
