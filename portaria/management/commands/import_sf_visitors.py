from django.core.management.base import BaseCommand
from django.db import transaction
from typing import Optional
from portaria.integrations.sf import fetch_visitor_logs
from portaria.models import VisitorLog
from condominio.models import Condominio, Unidade
from django.utils.dateparse import parse_datetime

# heurísticas de mapeamento (ajuste de acordo com seus campos no SF)
F_NAME = ["reda__VisitorName__c", "VisitorName__c", "Name"]
F_DOC  = ["reda__Document__c", "Document__c", "Documento__c"]
F_CHECKIN  = ["reda__CheckIn__c", "CheckIn__c", "Check_In__c"]
F_CHECKOUT = ["reda__CheckOut__c", "CheckOut__c", "Check_Out__c"]
F_CONDO = ["reda__Condominium__c", "Condominium__c", "Condo__c", "Condominio__c"]
F_UNIT  = ["reda__Unit__c", "Unit__c", "Unidade__c"]
F_CREATED = ["CreatedDate"]

def pick(rec: dict, keys: list[str]) -> Optional[str]:
    for k in keys:
        if k in rec and rec[k]:
            return rec[k]
    return None

class Command(BaseCommand):
    help = "Importa visitantes do Salesforce e grava em VisitorLog"

    def add_arguments(self, parser):
        parser.add_argument("--created", dest="created", default=None,
                            help='Filtro de data SF: TODAY, LAST_N_DAYS:30, 2025-09-01T00:00:00Z etc.')
        parser.add_argument("--limit", dest="limit", type=int, default=None,
                            help="Limite de registros")

    @transaction.atomic
    def handle(self, *args, **opts):
        created = opts.get("created")
        limit = opts.get("limit")
        recs = fetch_visitor_logs(created_filter=created, limit=limit)

        if not recs:
            self.stdout.write(self.style.WARNING("Nenhum registro retornado do SF."))
            return

        created_count = 0
        updated_count = 0

        for r in recs:
            sf_id = r.get("Id")
            nome = pick(r, F_NAME) or ""
            documento = pick(r, F_DOC) or ""

            # datas
            created_date_raw = pick(r, F_CREATED)
            created_date = parse_datetime(created_date_raw) if created_date_raw else None
            checkin_raw = pick(r, F_CHECKIN)
            checkout_raw = pick(r, F_CHECKOUT)
            checkin = parse_datetime(checkin_raw) if checkin_raw else None
            checkout = parse_datetime(checkout_raw) if checkout_raw else None

            # mapeamento condominio/unidade (opcional/heurístico)
            condominio = None
            unidade = None
            condo_name_or_id = pick(r, F_CONDO)
            unit_label = pick(r, F_UNIT)

            # Tente associar pelo nome (ajuste conforme seu dado)
            if condo_name_or_id:
                try:
                    condominio = Condominio.objects.filter(nome__iexact=condo_name_or_id).first()
                except Exception:
                    condominio = None

            if unit_label and condominio:
                try:
                    unidade = Unidade.objects.filter(bloco__condominio=condominio, numero__iexact=unit_label).first()
                except Exception:
                    unidade = None

            obj, created_flag = VisitorLog.objects.update_or_create(
                sf_id=sf_id,
                defaults={
                    "nome": nome,
                    "documento": documento,
                    "condominio": condominio,
                    "unidade": unidade,
                    "checkin": checkin,
                    "checkout": checkout,
                    "created_date": created_date,
                    "raw": r,
                },
            )
            if created_flag:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Importação concluída. Criados: {created_count}, Atualizados: {updated_count} (Total SF: {len(recs)})"
        ))
