from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Perfil
from django.contrib.auth.signals import user_logged_in, user_logged_out
from portaria.permissions import allowed_condominios_for
from django.db import transaction
from django.utils import timezone
from integrations.sf_tickets import sync_encomenda_to_salesforce


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Perfil.objects.create(user=instance)


@receiver(user_logged_in)
def put_condos_in_session(sender, request, user, **kwargs):
    """
    Ao logar, se NÃO for admin, grava na sessão:
      - allowed_condominios: [{id, nome}, ...]
      - allowed_condominio_ids: [id1, id2, ...]
    Se for admin/superuser, limpa essas chaves.
    """
    if user.is_superuser or user.groups.filter(name="Administrador").exists():
        request.session["is_admin_like"] = True
        request.session.pop("allowed_condominios", None)
        request.session.pop("allowed_condominio_ids", None)
        return

    qs = allowed_condominios_for(user).values("id", "nome")
    condos = list(qs)
    request.session["is_admin_like"] = False
    request.session["allowed_condominios"] = condos
    request.session["allowed_condominio_ids"] = [c["id"] for c in condos]

@receiver(user_logged_out)
def clear_condos_on_logout(sender, request, user, **kwargs):
    """Ao deslogar, limpa os dados da sessão relacionados a condomínios."""
    if request is None:
        return
    for key in ("allowed_condominios", "allowed_condominio_ids", "is_admin_like"):
        request.session.pop(key, None)


