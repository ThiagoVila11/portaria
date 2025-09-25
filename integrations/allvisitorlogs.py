import os
from typing import List, Dict, Optional
from simple_salesforce import Salesforce
import json
from core.params import get_param

SF_USERNAME = get_param("SF_USERNAME", "xx")
SF_PASSWORD = get_param("SF_PASSWORD", "xx")
SF_TOKEN    = get_param("SF_TOKEN", "xx")
SF_DOMAIN   = get_param("SF_DOMAIN", "xx")
SOBJECT = "reda__Visitor_Log__c"
JSON_OUT = "visitor_logs_dump.json"

CREATED_DATE_FILTER: Optional[str] = None  
LIMIT_RESULTS: Optional[int] = None


def sf_connect() -> Salesforce:
    return Salesforce(
        username=SF_USERNAME,
        password=SF_PASSWORD,
        security_token=SF_TOKEN,
        domain=SF_DOMAIN
    )

def get_all_fields(sf: Salesforce, sobject: str) -> List[str]:
    desc = sf.__getattr__(sobject).describe()
    fields = [f["name"] for f in desc["fields"]]
    if "Id" in fields:
        fields.remove("Id")
        fields = ["Id"] + fields
    return fields

def build_where_clause(created_filter: Optional[str]) -> str:
    """
    Sempre obriga reda__Permitted_Till_Datetime__c != null.
    Se CREATED_DATE_FILTER vier preenchido, inclui também o critério de data.
    """
    clauses = ["reda__Permitted_Till_Datetime__c != null"]

    if created_filter:
        cf = created_filter.upper()
        if cf in {"TODAY","YESTERDAY","THIS_WEEK","LAST_WEEK","THIS_MONTH","LAST_MONTH"} \
           or cf.startswith("LAST_N_DAYS:") or cf.startswith("NEXT_N_DAYS:"):
            clauses.append(f"CreatedDate = {cf}")
        else:
            clauses.append(f"CreatedDate >= {created_filter}")

    return " WHERE " + " AND ".join(clauses)

def query_chunk(sf: Salesforce, sobject: str, field_list: List[str], where_clause: str, limit: Optional[int]):
    soql = f"SELECT {', '.join(field_list)} FROM {sobject}{where_clause}"
    if limit:
        soql += f" LIMIT {int(limit)}"
    return sf.query_all(soql).get("records", [])

def main():
    sf = sf_connect()

    fields = get_all_fields(sf, SOBJECT)
    where_clause = build_where_clause(CREATED_DATE_FILTER)

    print(f"[INFO] Campos totais: {len(fields)}")
    print(f"[INFO] WHERE: {where_clause}")
    recs = query_chunk(sf, SOBJECT, fields, where_clause, LIMIT_RESULTS)
    for r in recs:
        r.pop("attributes", None)

    if not recs:
        print("[INFO] Nenhum registro encontrado.")
        return

    with open(JSON_OUT, "w", encoding="utf-8") as f:
        json.dump(recs, f, ensure_ascii=False, indent=2)

    print(f"[OK] Exportado {len(recs)} registros para {JSON_OUT}")

if __name__ == "__main__":
    main()