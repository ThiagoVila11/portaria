import base64
import os
from simple_salesforce import Salesforce
from integrations.allvisitorlogs import sf_connect

def anexar_arquivo_salesforce(file_path, ticket_id, titulo="Anexo"):
    """Envia um arquivo local para a Opportunity no Salesforce."""
    sf = sf_connect()
    if not os.path.exists(file_path):
        print(f"⚠️ Arquivo não encontrado: {file_path}")
        return None

    with open(file_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")

    # Cria ContentVersion
    filename = os.path.basename(file_path)
    content_data = {
        "Title": titulo,
        "PathOnClient": filename,
        "VersionData": encoded,
    }

    response = sf.ContentVersion.create(content_data)
    content_version_id = response.get("id")
    print(f"✅ ContentVersion criado: {content_version_id}")

    # Obtém o ContentDocumentId
    query = f"SELECT ContentDocumentId FROM ContentVersion WHERE Id = '{content_version_id}'"
    result = sf.query(query)
    content_doc_id = result["records"][0]["ContentDocumentId"]

    # Faz o vínculo com a Opportunity
    link_data = {
        "ContentDocumentId": content_doc_id,
        "LinkedEntityId": ticket_id,
        "ShareType": "V",
        "Visibility": "AllUsers",
    }
    sf.ContentDocumentLink.create(link_data)
    print(f"🔗 Arquivo {filename} vinculado à Opportunity {ticket_id}")
