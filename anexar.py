import os
import sys
import django
import base64

# 🧩 Configura o ambiente Django antes de qualquer import do projeto
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "condominio_portaria.settings")
django.setup()

# ✅ Só depois disso podemos importar coisas do seu projeto
from integrations.allvisitorlogs import sf_connect
from simple_salesforce import Salesforce

sf = sf_connect()

with open(r"C:\portaria\arquivos\brasilnet.pdf", "rb") as f:
    encoded = base64.b64encode(f.read()).decode("utf-8")

data = {
    "Title": "conta internet",
    "PathOnClient": "brasilnet.pdf",
    "VersionData": encoded,
}

response = sf.ContentVersion.create(data)
content_version_id = response.get("id")
print("✅ ContentVersion criado:", content_version_id)

query = f"SELECT ContentDocumentId FROM ContentVersion WHERE Id = '{content_version_id}'"
result = sf.query(query)
content_doc_id = result["records"][0]["ContentDocumentId"]
print("📄 ContentDocument:", content_doc_id)

opportunity_id = "006Np00000WIWyJIAX"  # ID da Opportunity no REDA

link_data = {
    "ContentDocumentId": content_doc_id,
    "LinkedEntityId": opportunity_id,
    "ShareType": "V",
    "Visibility": "AllUsers",
}

sf.ContentDocumentLink.create(link_data)
print("🔗 Arquivo vinculado à oportunidade com sucesso!")


