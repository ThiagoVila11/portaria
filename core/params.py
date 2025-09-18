# core/params.py
from django.core.cache import cache
from portaria.models import Parametro

def get_param(name: str, default=None, ttl=60):
    key = f"param:{name}"
    val = cache.get(key)
    if val is None:
        val = (Parametro.objects
               .filter(ParametroNome=name)
               .values_list("ParametroValor", flat=True)
               .first())
        cache.set(key, val, ttl)
    return val if val is not None else default
