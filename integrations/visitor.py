import os
import re
from typing import List, Dict, Optional
import pandas as pd
from simple_salesforce import Salesforce
import datetime
from core.params import get_param

# ==============================
# Config SF (variáveis de ambiente ou fallbacks)
# ==============================
SF_USERNAME = get_param("SF_USERNAME", "xx")
SF_PASSWORD = get_param("SF_PASSWORD", "xx")
SF_TOKEN    = get_param("SF_TOKEN", "xx")
SF_DOMAIN   = get_param("SF_DOMAIN", "xx")

# Nome do Objeto de Property (SObject) — AJUSTE se necessário
PROPERTY_SOBJECT = "reda__Property__c"
CSV_PROPERTIES = "properties_map.csv"

# ==============================
# Utils
# ==============================
def sf_connect() -> Salesforce:
    return Salesforce(
        username=SF_USERNAME,
        password=SF_PASSWORD,
        security_token=SF_TOKEN,
        domain="login"  # mude para "test" se for sandbox
    )

def normalize_phone_br(p: str) -> str:
    if not p:
        return ""
    digits = re.sub(r"\D", "", p)
    if digits.startswith("55") and len(digits) > 11:
        digits = digits[2:]
    return digits

def best_match_by_name(candidates: List[Dict], name: str) -> Optional[Dict]:
    if not candidates:
        return None
    name_low = name.strip().lower()
    exact = [c for c in candidates if (c.get("Name") or "").strip().lower() == name_low]
    if exact:
        return exact[0]
    starts = [c for c in candidates if (c.get("Name") or "").strip().lower().startswith(name_low)]
    if starts:
        return starts[0]
    contains = [c for c in candidates if name_low in (c.get("Name") or "").strip().lower()]
    if contains:
        return contains[0]
    return None

# ==============================
# Property helpers
# ==============================
def list_all_properties(sf: Salesforce, limit: int = 10000) -> List[Dict]:
    soql = f"SELECT Id, Name FROM {PROPERTY_SOBJECT} ORDER BY LastModifiedDate DESC LIMIT {int(limit)}"
    res = sf.query_all(soql)
    return res.get("records", [])

def save_properties_csv(props: List[Dict], path: str = CSV_PROPERTIES) -> None:
    rows = [{"Id": p["Id"], "Name": p.get("Name", "")} for p in props]
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False, encoding="utf-8")
    print(f"[INFO] Properties salvas em CSV: {path} (linhas: {len(rows)})")

# ==============================
# Resident (Contact) discovery
# ==============================
def find_account_property_lookup_field(sf: Salesforce) -> Optional[str]:
    """
    Verifica no Account se existe um lookup que referencia o SObject de Property.
    Retorna o API name (ex.: 'reda__Property__c') se existir.
    """
    desc = sf.Account.describe()
    for f in desc["fields"]:
        if f.get("type") == "reference":
            refs = f.get("referenceTo") or []
            if PROPERTY_SOBJECT in refs:
                return f["name"]
    return None

def list_contacts_for_property_via_account(sf: Salesforce, property_id: str, account_prop_field: str) -> List[Dict]:
    """
    Lista contatos onde Account.<lookup_prop> = property_id.
    """
    soql = f"""
        SELECT Id, Name, Phone, MobilePhone, Email, AccountId, Account.Name
        FROM Contact
        WHERE Account.{account_prop_field} = '{property_id}'
        ORDER BY LastModifiedDate DESC
        LIMIT 500
    """
    res = sf.query_all(soql)
    return res.get("records", [])

def search_contacts_by_name(sf: Salesforce, name_like: str) -> List[Dict]:
    """
    Busca contatos por nome (LIKE), caso não dê para filtrar por Property.
    """
    term = name_like.strip().replace("'", "\\'")
    soql = f"""
        SELECT Id, Name, Phone, MobilePhone, Email, AccountId, Account.Name
        FROM Contact
        WHERE Name LIKE '%{term}%'
        ORDER BY LastModifiedDate DESC
        LIMIT 100
    """
    res = sf.query_all(soql)
    return res.get("records", [])

# ==============================
# Visitor Log creation
# ==============================
from typing import Dict
from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceMalformedRequest
from datetime import datetime, timezone
import traceback

def criar_visitor_log_salesforce(
    sf: Salesforce,
    propriedade_id: str,
    oportunidade_id: str,
    contato_id: str,
    resultado: str,
    visitante_nome: str,
    visitante_endereco: str,
    visitante_telefone: str,
    visitante_email: str,
    visitante_tipo: str,
) -> Dict:
    sobj = sf.__getattr__("reda__Visitor_Log__c")
    print(f"Criando Visitor Log no Salesforce para Property {propriedade_id}, Contact {contato_id}")

    # ISO UTC sem micros, com Z
    received_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

    payload = {
        "reda__Status__c":        resultado,
        "reda__Property__c":      propriedade_id or None,
        "reda__Opportunity__c":   oportunidade_id or None,
        "reda__Contact__c":       contato_id or None,
        "Visitor_Type__c":        visitante_tipo or None,   # cuidado: confirme API Name
        "reda__Guest_Name__c":    visitante_nome,
        "reda__Guest_Email__c":   visitante_email or None,
        "reda__Guest_Phone__c":   visitante_telefone or None,
        #"reda__Check_In_Datetime__c": received_iso,
        #"Is_Pre_approved__c":     False,
        #"Is_Requested__c":        False,
    }

    # limpa nulos/vazios
    payload = {k: v for k, v in payload.items() if v not in (None, "", [])}
    print("Payload final:", payload)

    try:
        result = sobj.create(payload)
        print("✅ Registro criado:", result)
        return result
    except SalesforceMalformedRequest as e:
        print("❌ Erro de request malformado:")
        print("Conteúdo:", e.content)
        traceback.print_exc()
        return {"success": False, "error": e.content}
    except Exception as e:
        print("❌ Erro inesperado:")
        traceback.print_exc()
        return {"success": False, "error": str(e)}


def get_salesforce_connection():
    return sf_connect()  # já existe no visitor.py

# ==============================
# MAIN: Property -> Morador -> Visitor Log
# ==============================
def main():
    sf = sf_connect()

    # 1) Carregar Properties
    props = list_all_properties(sf)
    print(f"[INFO] Properties carregadas: {len(props)}")
    if not props:
        print("[ERRO] Nenhuma Property encontrada.")
        return
    save_properties_csv(props, CSV_PROPERTIES)

    print("\nAlgumas Properties recentes:")
    for p in props[:10]:
        print(f" - {p['Id']} | {p.get('Name')}")

    entrada = input("\nDigite o nome (ou parte) da Property: ").strip()
    cand = [p for p in props if entrada.lower() in (p.get("Name") or "").lower()]
    bm = best_match_by_name(cand if cand else props, entrada)
    if not bm:
        print("[ERRO] Property não encontrada.")
        return
    property_id = bm["Id"]
    property_name = bm.get("Name")
    print(f"[OK] Property selecionada: {property_name} ({property_id})")

    # 2) Descobrir relacionamento Account -> Property e listar moradores
    acc_prop_field = find_account_property_lookup_field(sf)
    contatos = []
    if acc_prop_field:
        contatos = list_contacts_for_property_via_account(sf, property_id, acc_prop_field)
        print(f"[INFO] Moradores (Contacts) vinculados à Property via Account.{acc_prop_field}: {len(contatos)}")
    else:
        print("[AVISO] Account não tem lookup p/ Property detectável. Vou buscar por nome de contato.")
        term = input("Digite parte do nome do morador (Contact): ").strip()
        contatos = search_contacts_by_name(sf, term)
        print(f"[INFO] Contatos encontrados pela busca: {len(contatos)}")

    # 3) Escolher morador
    host_contact_id = None
    if contatos:
        print("\nSelecione o morador (Contact):")
        for i, c in enumerate(contatos[:30], start=1):
            print(f" [{i}] {c.get('Name')} | Phone={c.get('Phone')} | Mobile={c.get('MobilePhone')} | Account={c.get('Account', {}).get('Name')}")
        escolha = input("Número (ou Enter para pular): ").strip()
        if escolha.isdigit():
            idx = int(escolha) - 1
            if 0 <= idx < len(contatos[:30]):
                host_contact_id = contatos[idx]["Id"]
                print(f"[OK] Morador selecionado: {contatos[idx]['Name']} ({host_contact_id})")

    if not host_contact_id:
        print("[AVISO] Nenhum morador selecionado. O Flow pode exigir um recipient (Contact).")

    # 4) Dados do visitante
    tel_in = input("\nTelefone do visitante (ex.: 11932138078, com ou sem +55/(), espaços): ").strip()
    tel_norm = normalize_phone_br(tel_in)
    nome_visitante = input("Nome do visitante: ").strip()
    endereco_visitante = input("Endereço do visitante: ").strip()
    email_visitante = input("Email do visitante (opcional): ").strip()

    # 5) Criar Visitor Log
    criar_visitor_log_salesforce(
        sf=sf,
        property_id=property_id,
        host_contact_id=host_contact_id,
        visitante_nome=nome_visitante,
        visitante_endereco=endereco_visitante,
        visitante_telefone=tel_norm,
        visitante_email=email_visitante
    )

if __name__ == "__main__":
    main()