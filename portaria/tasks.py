from celery import shared_task
from integrations.allvisitorlogs import sf_connect
from portaria.models import Encomenda

@shared_task
def atualizar_senhas_encomendas():
    """
    Sincroniza periodicamente o campo SenhaRetirada das encomendas com o Salesforce.
    """
    sf = sf_connect()
    total = 0
    erros = 0

    encomendas = Encomenda.objects.filter(
        salesforce_ticket_id__isnull=False
    ).exclude(salesforce_ticket_id="")

    for e in encomendas:
        try:
            soql = f"""
                SELECT Id, Password__c
                FROM reda__Ticket__c
                WHERE Id = '{e.salesforce_ticket_id}'
                AND Password__c != null
            """
            result = sf.query(soql).get("records", [])
            if result:
                senha = result[0].get("Password__c")
                if senha and e.SenhaRetirada != senha:
                    e.SenhaRetirada = senha
                    e.save(update_fields=["SenhaRetirada"])
                    total += 1
                    print(f"✅ Atualizado {e.id}: nova senha {senha}")
        except Exception as ex:
            erros += 1
            print(f"⚠️ Erro ao atualizar {e.id}: {ex}")

    print(f"📦 Atualização concluída: {total} encomendas atualizadas, {erros} erros.")
    return {"atualizadas": total, "erros": erros}
