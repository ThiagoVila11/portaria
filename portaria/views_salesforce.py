# portaria/views_salesforce.py
from datetime import datetime
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.contrib import messages
from django.utils.timezone import make_aware
from condominio.models import Condominio
from portaria.permissions import allowed_condominios_for
from integrations.sf_api import fetch_tickets, fetch_visitor_logs, resolve_sf_property_id

def _parse_date(s: str):
    if not s:
        return None
    try:
        # dia inteiro (00:00:00)
        dt = datetime.strptime(s, "%Y-%m-%d")
        return make_aware(dt)
    except Exception:
        return None

@login_required
def sf_tickets_list(request):
    allowed = allowed_condominios_for(request.user).order_by("nome")
    condominio_id = request.GET.get("condominio") or ""
    dt_ini = _parse_date(request.GET.get("dt_ini") or "")
    dt_fim = _parse_date(request.GET.get("dt_fim") or "")
    q = (request.GET.get("q") or "").strip()

    # default de condomínio para não-admins: primeiro permitido
    if not (request.user.is_superuser or request.user.groups.filter(name="Administrador").exists()):
        if not condominio_id:
            condominio_id = allowed.values_list("id", flat=True).first() or ""

    sf_property = resolve_sf_property_id(int(condominio_id)) if condominio_id else None
    tickets = []
    try:
        tickets = fetch_tickets(sf_property_id=sf_property, dt_ini=dt_ini, dt_fim=dt_fim, q=q, limit=500)
    except Exception as e:
        messages.error(request, f"Falha ao consultar Tickets no Salesforce: {e}")

    return render(request, "salesforce/tickets_list.html", {
        "tickets": tickets,
        "condominios": allowed,
        "q": {"condominio": condominio_id, "dt_ini": request.GET.get("dt_ini",""), "dt_fim": request.GET.get("dt_fim",""), "q": q},
        "total": len(tickets),
    })

@login_required
def sf_visitors_list(request):
    allowed = allowed_condominios_for(request.user).order_by("nome")
    condominio_id = request.GET.get("condominio") or ""
    dt_ini = _parse_date(request.GET.get("dt_ini") or "")
    dt_fim = _parse_date(request.GET.get("dt_fim") or "")
    q = (request.GET.get("q") or "").strip()

    if not (request.user.is_superuser or request.user.groups.filter(name="Administrador").exists()):
        if not condominio_id:
            condominio_id = allowed.values_list("id", flat=True).first() or ""

    sf_property = resolve_sf_property_id(int(condominio_id)) if condominio_id else None
    logs = []
    try:
        logs = fetch_visitor_logs(sf_property_id=sf_property, dt_ini=dt_ini, dt_fim=dt_fim, q=q, limit=500)
    except Exception as e:
        messages.error(request, f"Falha ao consultar Visitor’s Log no Salesforce: {e}")

    return render(request, "salesforce/visitors_list.html", {
        "logs": logs,
        "condominios": allowed,
        "q": {"condominio": condominio_id, "dt_ini": request.GET.get("dt_ini",""), "dt_fim": request.GET.get("dt_fim",""), "q": q},
        "total": len(logs),
    })
