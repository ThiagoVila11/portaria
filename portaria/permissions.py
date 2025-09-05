from condominio.models import Condominio

def allowed_condominios_for(user):
    if not user.is_authenticated:
        return Condominio.objects.none()
    if user.is_superuser or user.groups.filter(name="Administrador").exists():
        return Condominio.objects.all()
    return user.condominios_permitidos.all()
