# portaria/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction

from .models import Encomenda
from integrations.sf_tickets import sync_encomenda_to_salesforce

@receiver(post_save, sender=Encomenda)
def criar_ticket_sf_quando_criar_encomenda(sender, instance, created, **kwargs):
    if not created:
        return

    def _after_commit():
        try:
            ticket_id = sync_encomenda_to_salesforce(instance)
            if ticket_id:
                instance.salesforce_ticket_id = ticket_id
                instance.save(update_fields=["salesforce_ticket_id"])
        except Exception:
            pass

    transaction.on_commit(_after_commit)
