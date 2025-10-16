from django import template
from django.utils import timezone

register = template.Library()

@register.filter
def local_sp(value):
    """
    Converte um datetime UTC em horário local de São Paulo e formata.
    """
    if not value:
        return ""
    try:
        local_time = timezone.localtime(value)
        return local_time.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(value)
