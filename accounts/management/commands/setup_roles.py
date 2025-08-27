# accounts/management/commands/setup_roles.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from portaria.models import Encomenda

ROLE_MAP = {
    "BÁSICO":     ["view_encomenda"],
    "CONSULTOR":  ["view_encomenda", "add_encomenda", "change_encomenda"],
    "GERENTE":    ["view_encomenda", "add_encomenda", "change_encomenda", "delete_encomenda",
                   "pode_entregar_encomenda", "pode_receber_encomenda"],
    "ADMIN":      "ALL",  # recebe todas as permissões do app portaria (e outros que você quiser adicionar)
}

CUSTOM_PERMS = [
    ("pode_entregar_encomenda", "Pode entregar/baixar encomenda"),
    ("pode_receber_encomenda", "Pode receber/registrar chegada de encomenda"),
]

class Command(BaseCommand):
    help = "Cria/atualiza grupos e permissões para Encomenda (e afins). Use --reset para limpar permissões antes."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Limpa permissões existentes dos grupos antes de aplicar")

    def handle(self, *args, **opts):
        # 1) Garante que as permissões customizadas existem
        encomenda_ct = ContentType.objects.get_for_model(Encomenda)
        for codename, name in CUSTOM_PERMS:
            Permission.objects.get_or_create(
                content_type=encomenda_ct,
                codename=codename,
                defaults={"name": name},
            )

        # 2) Cria/limpa grupos
        groups = {}
        for gname in ROLE_MAP.keys():
            group, _ = Group.objects.get_or_create(name=gname)
            if opts["reset"]:
                group.permissions.clear()
            groups[gname] = group

        # 3) Admin recebe tudo do app 'portaria'
        if ROLE_MAP["ADMIN"] == "ALL":
            all_portaria_perms = Permission.objects.filter(content_type=encomenda_ct)
            groups["ADMIN"].permissions.add(*all_portaria_perms)

        # 4) Demais grupos recebem as permissões listadas
        def perm_by_codename(cn):
            qs = Permission.objects.filter(codename=cn)
            return qs.first()

        for gname, perm_list in ROLE_MAP.items():
            if perm_list == "ALL":
                continue
            for codename in perm_list:
                perm = perm_by_codename(codename)
                if perm:
                    groups[gname].permissions.add(perm)
                else:
                    self.stdout.write(self.style.WARNING(f"Permissão '{codename}' não encontrada; pulando."))

        # 5) Saída
        for name, g in groups.items():
            self.stdout.write(self.style.SUCCESS(f"Grupo '{name}': {g.permissions.count()} permissões."))
        self.stdout.write(self.style.SUCCESS("Roles/permissões configurados com sucesso."))
