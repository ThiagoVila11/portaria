# integrations/sf_ts.py
import os
from typing import Optional, Dict
from simple_salesforce import Salesforce
from portaria.models import Parametro
from django.conf import settings
from core.params import get_param
from integrations.salesforce_file import anexar_arquivo_salesforce

SF_USERNAME = get_param("SF_USERNAME", "xx")
SF_PASSWORD = get_param("SF_PASSWORD", "xx")
SF_TOKEN    = get_param("SF_TOKEN", "xx")
SF_DOMAIN   = get_param("SF_DOMAIN", "xx")

print(f"SF_USERNAME: {SF_USERNAME}")
print(f"SF_PASSWORD: {'set' if SF_PASSWORD else 'not set'}") 
print(f"SF_TOKEN: {'set' if SF_TOKEN else 'not set'}")
print(f"SF_DOMAIN: {SF_DOMAIN}")

def sf_connect() -> Salesforce:
    print("Conectando ao Salesforce sf_connect()...")
    if not all([SF_USERNAME, SF_PASSWORD, SF_TOKEN]):
        raise RuntimeError("Credenciais do Salesforce ausentes. Configure SF_USERNAME/SF_PASSWORD/SF_TOKEN.")
    return Salesforce(username=SF_USERNAME, password=SF_PASSWORD, security_token=SF_TOKEN)

def criar_t_salesforce(
    sf: Salesforce,
    property_id: str,
    contact_id: Optional[str],
    pacote_nome: str,
    pacote_para: str,
    pacote_desc: str,
    pacote_tipo: str,
    pacote_oportunidade: str,
) -> Dict:
    sobj = sf.__getattr__("reda__Ticket__c")

    # ISO UTC sem micros, com Z
    from datetime import datetime, timezone
    received_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

    payload = {
        # ajuste se precisar RecordType específico:
        "RecordTypeId": "012Np000000RgmLIAS",
        "reda__Property__c":            property_id,
        "reda__Contact__c":             contact_id or None,
        "reda__Package_Name__c":        pacote_nome or "",
        "reda__Package_For__c":         pacote_para or "",
        "reda__Package_Description__c": pacote_desc or "",
        "reda__Received_Date_Time__c":  received_iso,
        "reda__Opportunity__c":         pacote_oportunidade or "",
        "reda__Package_Name__c":        pacote_tipo or "",
    }
    # remove chaves None
    print(f"Payload para criar t: {payload}")
    payload = {k:v for k,v in payload.items() if v not in (None, "")}
    print(f"Payload filtrado: {payload}")
    teste = sobj.create(payload)
    print(f"Resposta da criação do t: {teste}")
    return teste

def build_package_fields_from_encomenda(encomenda) -> Dict[str, str]:
    print("Construindo campos do pacote a partir da encomenda...")
    """Deriva campos padrão a partir da Encomenda."""
    nome = getattr(encomenda, "codigo_rastreamento", "") or f"Encomenda {encomenda.pk}"
    para = getattr(getattr(encomenda, "destinatario", None), "nome", "") or str(getattr(encomenda, "destinatario", ""))
    desc = getattr(encomenda, "observacoes", "")
    tipo = getattr(encomenda, "PackageName", "")
    oportunidade = getattr(encomenda.destinatario, "sf_opportunity_id", "")
    return {"pacote_nome": nome, "pacote_para": para, "pacote_desc": desc, "pacote_tipo": tipo, "pacote_oportunidade": oportunidade}

def sync_encomenda_to_salesforce(encomenda) -> Optional[str]:
    print("Tentando criar t no Salesforce...")
    """
    Cria um reda__T__c no Salesforce a partir da Encomenda.
    Retorna o ID do t criado (ou None em caso de falha).
    """
    cond = encomenda.condominio
    unidades = encomenda.unidade
    print(cond.sf_property_id)
    print(f"Unidade: {unidades.sf_unidade_id if unidades else 'N/A'}")
    if not getattr(cond, "sf_property_id", ""):
        # Sem mapeamento para Property no SF: não é possível criar o t
        return None

    contact_id = None
    dest = getattr(encomenda, "destinatario", None)
    print(f"Destinatário: {dest}")
    print(f"SF Contact ID do destinatário: {getattr(dest, 'sf_contact_id', '') if dest else 'N/A'}")
    if dest and getattr(dest, "sf_contact_id", ""):
        contact_id = dest.sf_contact_id

    fields = build_package_fields_from_encomenda(encomenda)
    print(f"Campos do pacote: {fields}")
    sf = sf_connect()
    print("Conectado ao Salesforce. {sf}")
    res = criar_t_salesforce(
        sf=sf,
        property_id= unidades.sf_unidade_id,  #cond.sf_property_id,
        contact_id=contact_id,
        pacote_nome=fields["pacote_nome"],
        pacote_para=fields["pacote_para"],
        pacote_desc=fields["pacote_desc"],
        pacote_tipo=fields["pacote_tipo"],
        pacote_oportunidade=fields["pacote_oportunidade"]
    )
    if res.get("success"):
        if fields["pacote_oportunidade"]:
            opportunity_id = fields["pacote_oportunidade"]
            print(f"Anexando arquivos da encomenda {encomenda.id} à Opportunity {opportunity_id}...")
            base_dir = settings.MEDIA_ROOT
            print(f"Base dir: {base_dir}")
            for i in range(1, 6):
                print(f"Verificando arquivo {i}...")
                arquivo = getattr(encomenda, f"arquivo_0{i}")
                print(f"Arquivo {i}: {arquivo}")
                if arquivo:
                    file_path = os.path.join(base_dir, arquivo.name)
                    print(f"Caminho completo do arquivo {i}: {file_path}")
                    titulo = f"Encomenda {encomenda.id} - Arquivo {i}"
                    print(f"Anexando arquivo {file_path} com título '{titulo}'...")
                    anexar_arquivo_salesforce(file_path, opportunity_id, titulo)

        return res.get("id")
    return None

def delete_encomenda_from_salesforce(t_id: str) -> bool:
    """
    Exclui a encomenda no Salesforce pelo ID do t.
    Retorna True se excluiu com sucesso, False caso contrário.
    """
    print(f"Tentando excluir t {t_id} no Salesforce...")
    if not t_id:
        return False

    try:
        sf = sf_connect()  # 👈 reaproveita a função existente
        sf.reda__Ticket__c.delete(t_id)  # ajuste o objeto correto
        return True
    except Exception as e:
        print(f"⚠️ Erro ao excluir encomenda no Salesforce: {e}")
        return False
    
def delete_acesso_from_salesforce(sf_visitor_log: str) -> bool:
    """
    Exclui a encomenda no Salesforce pelo ID do t.
    Retorna True se excluiu com sucesso, False caso contrário.
    """
    print(f"Tentando excluir Acesso {sf_visitor_log} no Salesforce...")
    if not sf_visitor_log:
        return False

    try:
        sf = sf_connect()  # 👈 reaproveita a função existente
        sf.reda__Visitor_Log__c.delete(sf_visitor_log)  # ajuste o objeto correto
        return True
    except Exception as e:
        print(f"⚠️ Erro ao excluir acesso no Salesforce: {e}")
        return False


from django.utils import timezone

def update_encomenda_in_salesforce(encomenda):
    """
    Atualiza os campos de entrega da encomenda no Salesforce.
    """
    if not encomenda.salesforce_ticket_id:
        return False

    try:
        sf = sf_connect()

        # Monta payload
        data = {
            "reda__Package_Handed_on__c": encomenda.data_entrega.isoformat(),
            "reda__Package_Handed_To__c": encomenda.RetiradoPor,
            "reda__Status__c": "Handed Over",
        }

        # Atualiza no objeto correspondente
        # Ajuste o objeto para o correto da sua org (Case, T__c, Encomenda__c, etc.)
        sf.reda__Ticket__c.update(encomenda.salesforce_ticket_id, data)
        return True

    except Exception as e:
        print(f"⚠️ Erro ao atualizar encomenda no Salesforce: {e}")
        return False
