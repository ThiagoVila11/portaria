from integrations.allvisitorlogs import sf_connect, get_all_fields, build_where_clause, query_chunk, SOBJECT


def lista_contact_roles(request):
    sf = sf_connect()
    soql = """
        SELECT Id,
               reda__Contact__r.Name,
               reda__Guest_Name__c,
               reda__Property__c,
               reda__Property__r.Name,
               reda__Guest_Phone__c,
               CreatedDate,
               reda__Permitted_Till_Datetime__c
        FROM reda__Visitor_Log__c
        WHERE reda__Permitted_Till_Datetime__c != null
        ORDER BY CreatedDate DESC
        LIMIT 500
    """
    recs = sf.query_all(soql).get("records", [])
    print(recs)