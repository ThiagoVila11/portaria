# integrations/sf_tickets.py
import os
from typing import Optional, Dict
from simple_salesforce import Salesforce

from django.conf import settings

SF_USERNAME = getattr(settings, "SF_USERNAME", None)
SF_PASSWORD = getattr(settings, "SF_PASSWORD", None)
SF_TOKEN    = getattr(settings, "SF_TOKEN", None)
SF_DOMAIN   = getattr(settings, "SF_DOMAIN", "login")

def sf_connect() -> Salesforce:
    if not all([SF_USERNAME, SF_PASSWORD, SF_TOKEN]):
        raise RuntimeError("Credenciais do Salesforce ausentes. Configure SF_USERNAME/SF_PASSWORD/SF_TOKEN.")
    return Salesforce(username=SF_USERNAME, password=SF_PASSWORD, security_token=SF_TOKEN, domain=SF_DOMAIN)

def criar_ticket_salesforce(
    sf: Salesforce,
    property_id: str,
    contact_id: Optional[str],
    pacote_nome: str,
    pacote_para: str,
    pacote_desc: str,
) -> Dict:
    sobj = sf.__getattr__("reda__Ticket__c")

    # ISO UTC sem micros, com Z
    from datetime import datetime, timezone
    received_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

    payload = {
        # ajuste se precisar RecordType específico:
        # "RecordTypeId": "012Np000000RgmLIAS",
        "reda__Property__c":            property_id,
        "reda__Contact__c":             contact_id or None,
        "reda__Package_Name__c":        pacote_nome or "",
        "reda__Package_For__c":         pacote_para or "",
        "reda__Package_Description__c": pacote_desc or "",
        "reda__Received_Date_Time__c":  received_iso,
    }
    # remove chaves None
    payload = {k:v for k,v in payload.items() if v not in (None, "")}

    return sobj.create(payload)

def build_package_fields_from_encomenda(encomenda) -> Dict[str, str]:
    """Deriva campos padrão a partir da Encomenda."""
    nome = getattr(encomenda, "codigo_rastreamento", "") or f"Encomenda {encomenda.pk}"
    para = getattr(getattr(encomenda, "destinatario", None), "nome", "") or str(getattr(encomenda, "destinatario", ""))
    desc = " ".join(filter(None, [
        getattr(encomenda, "transportadora", ""),
        getattr(encomenda, "observacoes", "")
    ]))[:255]
    return {"pacote_nome": nome, "pacote_para": para, "pacote_desc": desc}

def sync_encomenda_to_salesforce(encomenda) -> Optional[str]:
    """
    Cria um reda__Ticket__c no Salesforce a partir da Encomenda.
    Retorna o ID do ticket criado (ou None em caso de falha).
    """
    cond = encomenda.condominio
    if not getattr(cond, "sf_property_id", ""):
        # Sem mapeamento para Property no SF: não é possível criar o ticket
        return None

    contact_id = None
    dest = getattr(encomenda, "destinatario", None)
    if dest and getattr(dest, "sf_contact_id", ""):
        contact_id = dest.sf_contact_id

    fields = build_package_fields_from_encomenda(encomenda)

    sf = sf_connect()
    res = criar_ticket_salesforce(
        sf=sf,
        property_id=cond.sf_property_id,
        contact_id=contact_id,
        pacote_nome=fields["pacote_nome"],
        pacote_para=fields["pacote_para"],
        pacote_desc=fields["pacote_desc"],
    )
    if res.get("success"):
        return res.get("id")
    return None
