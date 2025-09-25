from typing import Dict, Iterable, Optional, List
from django.core.cache import cache
from simple_salesforce import Salesforce
from condominio.models import Condominio
from portaria.models import Parametro  # ajuste se seu Parametro estiver em outro app

PARAM_TTL = 60
PARAM_KEYS = ["SF_USERNAME", "SF_PASSWORD", "SF_TOKEN", "SF_DOMAIN"]

def _fetch_params(keys: Iterable[str]) -> Dict[str, Optional[str]]:
    rows = (Parametro.objects
            .filter(ParametroNome__in=list(keys))
            .values_list("ParametroNome", "ParametroValor"))
    return {k: v for k, v in rows}

def get_params(keys: Iterable[str]) -> Dict[str, Optional[str]]:
    keys = list(keys)
    cache_key = "sf_params_v1"
    blob = cache.get(cache_key) or {}
    missing = [k for k in keys if k not in blob]
    if missing:
        fresh = _fetch_params(missing)
        blob.update(fresh)
        cache.set(cache_key, blob, PARAM_TTL)
    return {k: blob.get(k) for k in keys}

def sf_connect() -> Salesforce:
    p = get_params(PARAM_KEYS)
    username = p.get("SF_USERNAME")
    password = p.get("SF_PASSWORD")
    token    = p.get("SF_TOKEN")
    domain   = (p.get("SF_DOMAIN") or "login").strip()
    if not (username and password and token):
        raise RuntimeError("Credenciais SF ausentes em Parametro (SF_USERNAME, SF_PASSWORD, SF_TOKEN).")
    return Salesforce(username=username, password=password, security_token=token, domain=domain)

# Helpers de filtro
def resolve_sf_property_id(condominio_id: Optional[int]) -> Optional[str]:
    if not condominio_id:
        return None
    try:
        return Condominio.objects.only("sf_property_id").get(pk=condominio_id).sf_property_id or None
    except Condominio.DoesNotExist:
        return None

from datetime import datetime
from django.utils.timezone import make_naive

def _iso(dt: datetime) -> str:
    # SOQL usa UTC no formato 2025-09-10T00:00:00Z
    dt = make_naive(dt) if hasattr(dt, "tzinfo") and dt.tzinfo else dt
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def fetch_tickets(*, sf_property_id: Optional[str], dt_ini: Optional[datetime], dt_fim: Optional[datetime], q: str = "", limit: int = 500) -> List[dict]:
    sf = sf_connect()
    fields = [
        "Id", "Name", "CreatedDate", "LastModifiedDate",
        "reda__Status__c", "reda__Property__c",
        "reda__Package_Name__c", "reda__Package_For__c",
    ]
    where = ["reda__Status__c IN ('Handed Over','Received')"]
    if sf_property_id:
        where.append(f"reda__Property__c = '{sf_property_id}'")
    if dt_ini:
        where.append(f"CreatedDate >= { _iso(dt_ini) }")
    if dt_fim:
        where.append(f"CreatedDate <= { _iso(dt_fim) }")
    if q:
        # tentativa ampla: busca por Name/Package_For (ajuste conforme seu org)
        q_esc = q.replace("'", "\\'")
        where.append(f"(Name LIKE '%{q_esc}%' OR reda__Package_For__c LIKE '%{q_esc}%')")

    soql = f"""
      SELECT {", ".join(fields)}
      FROM reda__Ticket__c
      WHERE {" AND ".join(where)}
      ORDER BY CreatedDate DESC
      LIMIT {int(limit)}
    """
    recs = sf.query_all(soql).get("records", [])
    for r in recs:
        r.pop("attributes", None)
    return recs

# --- NOVO helper: escolher campos que existem via describe --------------------
def _pick_fields(sf_obj, candidates):
    """
    Retorna a primeira opção de candidates que existir no objeto (ou None).
    candidates pode ser string ou lista de strings (ordem de preferência).
    """
    if isinstance(candidates, str):
        candidates = [candidates]
    # faça um describe só uma vez
    desc = sf_obj.describe()
    available = {f["name"] for f in desc.get("fields", [])}
    for c in candidates:
        if c in available:
            return c
    return None


# --- SUBSTITUA sua fetch_visitor_logs por esta versão robusta -----------------
def fetch_visitor_logs(*, sf_property_id: Optional[str], dt_ini: Optional[datetime], dt_fim: Optional[datetime], q: str = "", limit: int = 500) -> List[dict]:
    sf = sf_connect()
    obj = sf.__getattr__("reda__Visitor_Log__c")  # objeto alvo

    # Descobre nomes reais de campos no seu org (se existirem)
    fld_property   = _pick_fields(obj, ["reda__Property__c", "Property__c"])
    fld_visitor    = "" #_pick_fields(obj, ["reda__Visitor_Name__c", "Visitor_Name__c", "VisitorName__c", "reda__Visitor__c", "Contact__c", "reda__Contact__c"])
    fld_access     = _pick_fields(obj, ["reda__Access_Type__c", "Access_Type__c", "AccessType__c"])
    fld_result     = _pick_fields(obj, ["reda__Result__c", "Result__c", "Access_Result__c"])

    # Campos sempre presentes
    select_fields = ["Id", "Name", "CreatedDate"]
    # Campos opcionais (só adiciona se existirem)
    for fx in (fld_property, fld_visitor, fld_access, fld_result):
        if fx:
            select_fields.append(fx)

    where = []
    if sf_property_id and fld_property:
        where.append(f"{fld_property} = '{sf_property_id}'")
    if dt_ini:
        where.append(f"CreatedDate >= { _iso(dt_ini) }")
    if dt_fim:
        where.append(f"CreatedDate <= { _iso(dt_fim) }")
    if q:
        q_esc = q.replace("'", "\\'")
        like_terms = [f"Name LIKE '%{q_esc}%'"]
        if fld_visitor:
            like_terms.append(f"{fld_visitor} LIKE '%{q_esc}%'")
        where.append("(" + " OR ".join(like_terms) + ")")

    soql = f"""
      SELECT {", ".join(select_fields)}
      FROM reda__Visitor_Log__c
      {"WHERE " + " AND ".join(where) if where else ""}
      ORDER BY CreatedDate DESC
      LIMIT {int(limit)}
    """
    recs = sf.query_all(soql).get("records", [])
    for r in recs:
        r.pop("attributes", None)
    return recs
