# core/params.py
#from django.core.cache import cache
#from portaria.models import Parametro

#def get_param(name: str, default=None, ttl=60):
#    key = f"param:{name}"
#    val = cache.get(key)
#    if val is None:
#        val = (Parametro.objects
#               .filter(ParametroNome=name)
#               .values_list("ParametroValor", flat=True)
#               .first())
#        cache.set(key, val, ttl)
#    return val if val is not None else default

from django.db.utils import OperationalError, ProgrammingError


def get_param(key, default=None):
    """
    Busca um parâmetro da tabela Parametro.
    Se o banco ainda não estiver pronto (sem tabela/migrações), retorna o default.
    """
    try:
        from portaria.models import Parametro
        val = (
            Parametro.objects
            .filter(chave=key)
            .values_list("valor", flat=True)
            .first()
        )
        return val if val is not None else default
    except (OperationalError, ProgrammingError):
        # Banco não disponível ou tabela não criada ainda
        return default
