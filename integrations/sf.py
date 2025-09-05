from typing import List, Optional
from simple_salesforce import Salesforce
from django.conf import settings

def sf_connect() -> Salesforce:
    return Salesforce(
        username=settings.SF["USERNAME"],
        password=settings.SF["PASSWORD"],
        security_token=settings.SF["TOKEN"],
        domain=settings.SF["DOMAIN"],
    )

def get_all_fields(sf: Salesforce, sobject: str) -> List[str]:
    desc = getattr(sf, sobject).describe()
    fields = [f["name"] for f in desc["fields"]]
    if "Id" in fields:
        fields.remove("Id")
        fields = ["Id"] + fields
    return fields

def build_where_clause(created_filter: Optional[str]) -> str:
    if not created_filter:
        return ""
    cf = created_filter.upper()
    if cf in {"TODAY","YESTERDAY","THIS_WEEK","LAST_WEEK","THIS_MONTH","LAST_MONTH"} \
       or cf.startswith("LAST_N_DAYS:") or cf.startswith("NEXT_N_DAYS:"):
        return f" WHERE CreatedDate = {cf}"
    return f" WHERE CreatedDate >= {created_filter}"

def fetch_visitor_logs(created_filter: Optional[str] = None, limit: Optional[int] = None) -> List[dict]:
    sf = sf_connect()
    sobject = settings.SF["SOBJECT"]
    fields = get_all_fields(sf, sobject)
    where_clause = build_where_clause(created_filter)
    soql = f"SELECT {', '.join(fields)} FROM {sobject}{where_clause}"
    if limit:
        soql += f" LIMIT {int(limit)}"
    recs = sf.query_all(soql).get("records", [])
    for r in recs:
        r.pop("attributes", None)
    return recs
