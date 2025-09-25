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
def criar_visitor_log_salesforce(
    sf: Salesforce,
    property_id: str,
    host_contact_id: Optional[str],
    visitante_nome: str,
    visitante_endereco: str,
    visitante_telefone: str,
    visitante_email: str = ""
) -> Dict:
    """
    Cria reda__Visitor_Log__c preenchendo:
      - reda__Property__c (obrigatório)
      - reda__Status__c = "Requested" (se createable e valor permitido)
      - reda__Check_In_Datetime__c = agora (UTC, ISO 8601)
      - lookup p/ Contact (morador/host), se existir campo createable e host_contact_id for informado
      - descrição + possíveis campos Visitor_* se existirem
      - booleans obrigatórios createable como False
    """
    sobj = sf.__getattr__("reda__Visitor_Log__c")
    desc = sobj.describe()
    campos_info = {f["name"]: f for f in desc["fields"]}

    # ===== 1) Monta candidatos base =====
    candidatos = {
        "reda__Property__c": property_id,
    }

    # ===== 2) Status = Requested (validando picklist) =====
    status_info = campos_info.get("reda__Status__c")
    if status_info and status_info.get("createable"):
        vs = status_info.get("picklistValues") or []
        allowed = [v["value"] for v in vs if not v.get("inactive", False)] if vs else None
        if (allowed is None) or ("Requested" in set(allowed)):
            candidatos["reda__Status__c"] = "Requested"
        else:
            print("[AVISO] 'Requested' não está entre os valores do picklist de reda__Status__c.",
                  "Valores permitidos:", ", ".join(allowed) if allowed else "(não retornou lista)")
    else:
        print("[AVISO] Campo reda__Status__c não é createable ou não existe; pulando o set de Status.")

    # ===== 3) Check-in agora (UTC) =====
    checkin_field = "reda__Check_In_Datetime__c"
    if checkin_field in campos_info and campos_info[checkin_field].get("createable"):
        now_utc_iso = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
        # troca +00:00 por Z para o padrão ISO aceito
        if now_utc_iso.endswith("+00:00"):
            now_utc_iso = now_utc_iso.replace("+00:00", "Z")
        candidatos[checkin_field] = now_utc_iso
        print(f"[INFO] Check-in datetime setado: {now_utc_iso}")
    else:
        print("[AVISO] Campo reda__Check_In_Datetime__c não é createable ou não existe; pulando.")

    # ===== 4) Lookup p/ Contact (morador/host) =====
    ref_contact_fields = []
    for f in desc["fields"]:
        if f.get("type") == "reference" and f.get("createable", False):
            refs = f.get("referenceTo") or []
            if "Contact" in refs:
                ref_contact_fields.append(f["name"])

    if host_contact_id and ref_contact_fields:
        def sort_key(x):
            lower = x.lower()
            return (0 if "host" in lower else (1 if "contact" in lower else 2), x)
        ref_contact_fields.sort(key=sort_key)
        candidatos[ref_contact_fields[0]] = host_contact_id
        print(f"[INFO] Lookup host (Contact) usado: {ref_contact_fields[0]} = {host_contact_id}")
    elif host_contact_id and not ref_contact_fields:
        print("[AVISO] Não há lookup createable para Contact em reda__Visitor_Log__c; o Flow pode exigir um recipient.")
        
    # ===== 4.1) Guest fields específicos =====
    if visitante_nome:
        if "reda__Guest_Name__c" in campos_info and campos_info["reda__Guest_Name__c"].get("createable"):
            candidatos["reda__Guest_Name__c"] = visitante_nome
            print("[INFO] Preenchido Guest Name em reda__Guest_Name__c")

    if visitante_telefone:
        if "reda__Guest_Phone__c" in campos_info and campos_info["reda__Guest_Phone__c"].get("createable"):
            candidatos["reda__Guest_Phone__c"] = visitante_telefone
            print("[INFO] Preenchido Guest Phone em reda__Guest_Phone__c")

    if visitante_email:
        if "reda__Guest_Email__c" in campos_info and campos_info["reda__Guest_Email__c"].get("createable"):
            candidatos["reda__Guest_Email__c"] = visitante_email
            print("[INFO] Preenchido Guest Email em reda__Guest_Email__c")

    # ===== 5) Campos de texto (descrição + Visitor_*) =====
    descricao = (
        f"Visitante: {visitante_nome or '(vazio)'} | "
        f"Telefone: {visitante_telefone or '(vazio)'} | "
        f"Email: {visitante_email or '(vazio)'} | "
        f"Endereço: {visitante_endereco or '(vazio)'}"
    )
    for campo_desc in [
        "reda__Description__c", "Description__c", "Description",
        "Notes__c", "Notes", "Comment__c", "Comment",
        "Remarks__c", "Remarks",
    ]:
        info = campos_info.get(campo_desc)
        if info and info.get("createable"):
            candidatos[campo_desc] = descricao
            break

    visitor_text_map = [
        ("nome", visitante_nome,    ["reda__Visitor_Name__c","Visitor_Name__c","VisitorName__c","Visitor__c","Name_Text__c"]),
        ("telefone", visitante_telefone, ["reda__Visitor_Phone__c","Visitor_Phone__c","Phone__c","VisitorPhone__c","Phone_Text__c"]),
        ("email", visitante_email,  ["reda__Visitor_Email__c","Visitor_Email__c","Email__c","VisitorEmail__c","Email_Text__c"]),
        ("endereco", visitante_endereco, ["reda__Visitor_Address__c","Visitor_Address__c","Address__c"]),
    ]
    for label, value, campos in visitor_text_map:
        if not value:
            continue
        for fn in campos:
            info = campos_info.get(fn)
            if info and info.get("createable"):
                candidatos.setdefault(fn, value)
                print(f"[INFO] Preenchido {label} em: {fn}")
                break

    # ===== 6) Booleans obrigatórios createable = False =====
    for f in desc["fields"]:
        if f.get("type") == "boolean" and not f.get("nillable", True) and f.get("createable", False):
            candidatos.setdefault(f["name"], False)

    # ===== 7) Filtra payload e cria =====
    payload = {k: v for k, v in candidatos.items() if k in campos_info and campos_info[k].get("createable")}
    if "reda__Property__c" not in payload:
        raise RuntimeError("reda__Property__c não está createable ou não existe no seu org.")

    print("[INFO] Visitor_Log payload:", ", ".join(payload.keys()))
    res = sobj.create(payload)
    print("[RESP SF Visitor_Log]:", res)
    return res

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