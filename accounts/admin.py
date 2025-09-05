from django.contrib import admin
from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserCreationForm
from condominio.models import Condominio
from .models import Perfil

User = get_user_model()

# --- Perfil admin (mantido) ---
@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display = ("user", "nivel")
    list_filter = ("nivel",)

# --- Helpers para “limpar” fieldsets viciados (ex.: usable_password) ---
def _strip_field_from_fieldsets(fieldsets, bad_field="usable_password"):
    cleaned = []
    for name, opts in fieldsets:
        opts = dict(opts)  # copia raso
        fields = opts.get("fields")
        if isinstance(fields, (list, tuple)):
            # pode ser lista simples ou tuplas aninhadas (grupos)
            new_fields = []
            for item in fields:
                if isinstance(item, (list, tuple)):
                    item = tuple(f for f in item if f != bad_field)
                    if item:
                        new_fields.append(item)
                else:
                    if item != bad_field:
                        new_fields.append(item)
            opts["fields"] = tuple(new_fields)
        cleaned.append((name, opts))
    return tuple(cleaned)

# --- Forms com condomínios ---
class UserChangeWithCondosForm(forms.ModelForm):
    condominios_permitidos = forms.ModelMultipleChoiceField(
        label="Condomínios com acesso",
        queryset=Condominio.objects.all(),
        required=False,
        widget=FilteredSelectMultiple("Condomínios", is_stacked=False),
    )
    class Meta:
        model = User
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["condominios_permitidos"].initial = self.instance.condominios_permitidos.all()

    def save(self, commit=True):
        user = super().save(commit=commit)
        if not user.pk:
            user.save()
        user.condominios_permitidos.set(self.cleaned_data.get("condominios_permitidos", []))
        return user

class UserAddWithCondosForm(UserCreationForm):
    condominios_permitidos = forms.ModelMultipleChoiceField(
        label="Condomínios com acesso",
        queryset=Condominio.objects.all(),
        required=False,
        widget=FilteredSelectMultiple("Condomínios", is_stacked=False),
    )
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def save(self, commit=True):
        user = super().save(commit=commit)
        if not user.pk:
            user.save()
        user.condominios_permitidos.set(self.cleaned_data.get("condominios_permitidos", []))
        return user

# --- UserAdmin custom, com fieldsets “limpos” ---
class UserAdmin(BaseUserAdmin):
    form = UserChangeWithCondosForm
    add_form = UserAddWithCondosForm

    # Clona os fieldsets base e remove qualquer 'usable_password' que alguém tenha injetado
    base_fieldsets_clean  = _strip_field_from_fieldsets(BaseUserAdmin.fieldsets)
    base_addsets_clean    = _strip_field_from_fieldsets(BaseUserAdmin.add_fieldsets)

    fieldsets = base_fieldsets_clean + (
        ("Acesso por Condomínio", {"fields": ("condominios_permitidos",)}),
    )
    add_fieldsets = base_addsets_clean + (
        ("Acesso por Condomínio", {"classes": ("wide",), "fields": ("condominios_permitidos",)}),
    )

# Garante que o UserAdmin ativo seja ESTE
try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass
admin.site.register(User, UserAdmin)
