from django.contrib.auth.decorators import login_required, permission_required
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from portaria.permissions import allowed_condominios_for
from django.utils import timezone
from .models import Encomenda, EventoAcesso, StatusEncomenda, TipoPessoa, MetodoAcesso, ResultadoAcesso, Veiculo
from condominio.models import Condominio, Unidade, Morador, Bloco
from portaria.models import EventoAcesso, Encomenda
from condominio.models import Condominio, Unidade
from django.utils.dateparse import parse_date
from django.contrib import messages
from portaria.forms import EncomendaForm, EventoAcessoForm
from integrations.sf_tickets import sync_encomenda_to_salesforce, delete_encomenda_from_salesforce, update_encomenda_in_salesforce, delete_acesso_from_salesforce
from integrations.visitor import get_salesforce_connection, criar_visitor_log_salesforce
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest
from datetime import date
from integrations.allvisitorlogs import sf_connect, get_all_fields, build_where_clause, query_chunk, SOBJECT
from .forms import VeiculoForm
from django.http import JsonResponse
from collections import OrderedDict

@login_required
def dashboard(request):
    ctx = {
    'total_encomendas': Encomenda.objects.count(),
    'encomendas_pendentes': Encomenda.objects.filter(status=StatusEncomenda.RECEBIDA).count(),
    'acessos_hoje': EventoAcesso.objects.filter(criado_em__date=timezone.now().date()).count(),
    }
    return render(request, 'portaria/dashboard.html', ctx)


#@login_required
#def encomenda_list(request):
#    encomendas = Encomenda.objects.select_related('destinatario', 'unidade', 'condominio').order_by('-data_recebimento')
#    return render(request, 'portaria/encomenda_list.html', {'encomendas': encomendas})

# portaria/views.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils.dateparse import parse_date
from django.db import models  # <- para detectar FK
from portaria.permissions import allowed_condominios_for
from .models import Encomenda

@login_required
def encomenda_list(request):
    allowed = allowed_condominios_for(request.user)
    is_admin_like = request.user.is_superuser or request.user.groups.filter(name="Administrador").exists()

    qs = (Encomenda.objects
          .select_related("condominio", "unidade", "destinatario")
          .filter(condominio__in=allowed))

    # --- valores vindos do GET (se houver) ---
    condominio_id  = request.GET.get("condominio")
    dt_ini         = request.GET.get("dt_ini")
    dt_fim         = request.GET.get("dt_fim")
    destinatario_q = request.GET.get("destinatario")

    # Detecta "primeira carga": nenhum filtro no GET
    initial_load = not any(k in request.GET for k in ["condominio", "dt_ini", "dt_fim", "destinatario"])

    if initial_load:
        hoje = timezone.localdate()             # objeto date
        dt_ini = hoje.replace(day=1).isoformat()  # 'YYYY-MM-01'
        dt_fim = hoje.isoformat()                 # 'YYYY-MM-DD'

        if not is_admin_like:
            first_allowed_id = allowed.order_by("nome").values_list("id", flat=True).first()
            condominio_id = str(first_allowed_id) if first_allowed_id else ""

    # --- aplica filtros ---
    if condominio_id:
        qs = qs.filter(condominio_id=condominio_id)

    if dt_ini:
        d0 = parse_date(str(dt_ini))
        if d0:
            qs = qs.filter(data_recebimento__date__gte=d0)

    if dt_fim:
        d1 = parse_date(str(dt_fim))
        if d1:
            qs = qs.filter(data_recebimento__date__lte=d1)

    if destinatario_q:
        field = Encomenda._meta.get_field("destinatario")
        if isinstance(field, models.ForeignKey):
            qs = qs.filter(destinatario__nome__icontains=destinatario_q)
        else:
            qs = qs.filter(destinatario__icontains=destinatario_q)

    qs = qs.order_by("-data_recebimento")

    ctx = {
        "encomendas": qs,
        "condominios": allowed,
        "q": {
            "condominio": condominio_id or "",
            "dt_ini": dt_ini or "",
            "dt_fim": dt_fim or "",
            "destinatario": destinatario_q or "",
        },
        "total": qs.count(),
    }
    return render(request, "portaria/encomenda_list.html", ctx)


@login_required
def encomenda_create(request):
    print("Acessando encomenda_create")
    allowed_condominios = allowed_condominios_for(request.user)

    if request.method == "POST":
        form = EncomendaForm(
            request.POST,
            request.FILES,
            user=request.user,
            is_create=True,
            allowed_condominios=allowed_condominios,
        )
        if form.is_valid():
            encomenda = form.save(commit=False)
            encomenda.status = "RECEBIDA"
            encomenda.recebido_por = request.user
            if not encomenda.data_recebimento:
                encomenda.data_recebimento = timezone.now()
            encomenda.save()

            # 🔑 só sincroniza se ainda não estiver integrado
            if not encomenda.salesforce_ticket_id:
                print("Tentando integrar com Salesforce...")
                try:
                    ticket_id = sync_encomenda_to_salesforce(encomenda)
                    print(f"Resultado da integração com Salesforce: {ticket_id}")
                    if ticket_id:
                        encomenda.salesforce_ticket_id = ticket_id
                        encomenda.save(update_fields=["salesforce_ticket_id"])
                        messages.info(request, f"Ticket criado no Salesforce: {ticket_id}")
                except Exception:
                    messages.warning(request, "Encomenda salva, mas houve erro ao integrar com o Salesforce.")
            else:
                print(f"Encomenda já integrada com Salesforce: {encomenda.salesforce_ticket_id}")

            messages.success(request, f"Encomenda {encomenda.pk} criada com sucesso.")
            return redirect("encomenda_list")
    else:
        form = EncomendaForm(
            user=request.user,
            is_create=True,
            allowed_condominios=allowed_condominios,
        )

    return render(request, "portaria/encomenda_form.html", {"form": form})


@login_required
#@permission_required('portaria.pode_entregar_encomenda', raise_exception=True)
def encomenda_entregar(request, pk):
    enc = get_object_or_404(Encomenda, pk=pk)
    if request.method == 'POST':
        enc.status = StatusEncomenda.ENTREGUE
        enc.data_entrega = timezone.now()
        enc.entregue_por = request.user
        enc.save()
        # 🔑 Atualizar no Salesforce
        ok = update_encomenda_in_salesforce(enc)
        if not ok:
            messages.warning(request, "Encomenda entregue localmente, mas não foi possível atualizar no Salesforce.")
        else:
            messages.success(request, f"Encomenda #{enc.pk} entregue e sincronizada no Salesforce.")
    return render(request, 'portaria/encomenda_entregar_confirm.html', {'encomenda': enc})

@login_required
@require_POST
def encomenda_delete(request, pk):
    allowed = allowed_condominios_for(request.user)
    encomenda = get_object_or_404(Encomenda, pk=pk, condominio__in=allowed)

    # tenta excluir no Salesforce antes de apagar localmente
    if encomenda.salesforce_ticket_id:
        ok = delete_encomenda_from_salesforce(encomenda.salesforce_ticket_id)
        if ok:
            messages.info(request, f"Encomenda também excluída no Salesforce (ID {encomenda.salesforce_ticket_id}).")
        else:
            messages.warning(request, f"Encomenda excluída localmente, mas falhou ao excluir no Salesforce.")

    encomenda.delete()
    messages.success(request, f"Encomenda #{pk} excluída com sucesso.")
    return redirect("encomenda_list")



from datetime import date
from django.utils import timezone
from django.utils.dateparse import parse_date

@login_required
def acesso_list(request):
    allowed = allowed_condominios_for(request.user)
    is_admin_like = request.user.is_superuser or request.user.groups.filter(name="Administrador").exists()

    qs = (EventoAcesso.objects
          .select_related("condominio", "unidade")
          .filter(condominio__in=allowed))

    # Valores vindos do GET (se houver)
    condominio_id = request.GET.get("condominio")
    dt_ini        = request.GET.get("dt_ini")
    dt_fim        = request.GET.get("dt_fim")
    nome_q        = request.GET.get("nome")

    # Primeira carga: nenhum filtro no GET
    initial_load = not any(k in request.GET for k in ["condominio", "dt_ini", "dt_fim", "nome"])
    if initial_load:
        hoje = timezone.localdate()
        dt_ini = hoje.replace(day=1).isoformat()   # string: "2025-09-01"
        dt_fim = hoje.isoformat()                  # string: "2025-09-23"
        if not is_admin_like:
            first_allowed_id = allowed.order_by("nome").values_list("id", flat=True).first()
            condominio_id = str(first_allowed_id) if first_allowed_id else ""

    # Aplica filtros
    if condominio_id:
        qs = qs.filter(condominio_id=condominio_id)

    if dt_ini:
        d0 = parse_date(str(dt_ini))
        if d0:
            qs = qs.filter(criado_em__date__gte=d0)

    if dt_fim:
        d1 = parse_date(str(dt_fim))
        if d1:
            qs = qs.filter(criado_em__date__lte=d1)

    if nome_q:
        qs = qs.filter(pessoa_nome__icontains=nome_q)

    qs = qs.order_by("-criado_em")

    ctx = {
        "eventos": qs,
        "condominios": allowed,
        "q": {
            "condominio": condominio_id or "",
            "dt_ini": dt_ini or "",
            "dt_fim": dt_fim or "",
            "nome": nome_q or "",
        },
        "total": qs.count(),
    }
    return render(request, "portaria/acesso_list.html", ctx)


@login_required
def acesso_create(request):
    if request.method == "POST":
        form = EventoAcessoForm(request.POST, user=request.user)
        if form.is_valid():
            acesso = form.save(commit=False)
            acesso.criado_por = request.user  # 🔹 preencher aqui
            acesso.save()

            # integração Salesforce...
            if not acesso.sf_visitor_log_id:
                try:
                    sf = get_salesforce_connection() 
                    #ticket_id = sync_encomenda_to_salesforce(encomenda)
                    print("Tentando criar VisitorLog no Salesforce...")
                    visitor_log_id = criar_visitor_log_salesforce(
                        sf=sf,
                        propriedade_id= acesso.unidade.sf_unidade_id, 
                        oportunidade_id = acesso.responsavel.sf_opportunity_id,
                        contato_id = acesso.responsavel.sf_contact_id,
                        resultado = acesso.resultado,
                        visitante_nome=acesso.pessoa_nome,
                        visitante_endereco=str(acesso.unidade) if acesso.unidade else "",
                        visitante_telefone=acesso.pessoa_telefone,
                        visitante_email="",
                        visitante_tipo=acesso.pessoa_tipo,
                    )
                    print(f"VisitorLog criado no Salesforce: {visitor_log_id}")
                    if visitor_log_id:
                        id_visita = visitor_log_id["id"]
                        acesso.sf_visitor_log_id = id_visita
                        acesso.save(update_fields=["sf_visitor_log_id"])
                        messages.info(request, f"Visitante criado no Salesforce: {id_visita}")
                    messages.success(request, "Acesso registrado e enviado ao Salesforce. {id_visita}")
                except Exception as e:
                    messages.error(request, f"Acesso salvo, mas falhou integração SF: {e}")

            return redirect("acesso_list")
    else:
        form = EventoAcessoForm(user=request.user)

    return render(request, "portaria/acesso_form.html", {"form": form})

@login_required
#@permission_required('portaria.delete_eventoacesso', raise_exception=True)
@require_POST
def acesso_delete(request, pk):
    allowed = allowed_condominios_for(request.user)
    evento = get_object_or_404(EventoAcesso, pk=pk, condominio__in=allowed)

    # tenta excluir no Salesforce antes de apagar localmente
    if evento.sf_visitor_log_id:
        ok = delete_acesso_from_salesforce(evento.sf_visitor_log_id)
        if ok:
            messages.info(request, f"Acesso também excluído no Salesforce (ID {evento.sf_visitor_log_id}).")
        else:
            messages.warning(request, f"Acesso excluído localmente, mas falhou ao excluir no Salesforce.")

    evento.delete()
    messages.success(request, 'Registro de acesso excluído com sucesso.')
    return redirect('acesso_list')


@login_required
#@permission_required("portaria.change_encomenda", raise_exception=True)
def encomenda_edit(request, pk):
    allowed = allowed_condominios_for(request.user)
    encomenda = get_object_or_404(Encomenda, pk=pk, condominio__in=allowed)

    if request.method == "POST":
        form = EncomendaForm(request.POST, request.FILES, instance=encomenda, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f"Encomenda {encomenda.pk} atualizada com sucesso.")
            return redirect("encomenda_list")
    else:
        form = EncomendaForm(instance=encomenda, user=request.user)

    return render(request, "portaria/encomenda_form.html", {"form": form, "obj": encomenda})

@login_required
#@permission_required("portaria.change_eventoacesso", raise_exception=True)
def acesso_edit(request, pk):
    allowed = allowed_condominios_for(request.user)
    evento = get_object_or_404(EventoAcesso, pk=pk, condominio__in=allowed)

    if request.method == "POST":
        form = EventoAcessoForm(request.POST, instance=evento, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Registro de acesso atualizado com sucesso.")
            return redirect("acesso_list")

        return render(request, "portaria/acesso_form.html", {"form": form, "obj": evento}, status=400)

    # GET sempre retorna o form preenchido
    form = EventoAcessoForm(instance=evento, user=request.user)
    return render(request, "portaria/acesso_form.html", {"form": form, "obj": evento})

@login_required
def ajax_unidades_por_condominio(request, condominio_id: int):
    unidades = (Unidade.objects
                .filter(bloco__condominio_id=condominio_id)
                .select_related("bloco")
                .order_by("bloco__nome", "numero"))

    options = ['<option value="">—</option>']
    for u in unidades:
        options.append(f'<option value="{u.id}">{u}</option>')
    return HttpResponse("".join(options), content_type="text/html")


@login_required
def ajax_moradores_por_unidade(request, unidade_id: int):
    moradores = (Morador.objects
                 .filter(unidade_id=unidade_id, ativo=True)
                 .order_by("nome"))

    options = ['<option value="">—</option>']
    for m in moradores:
        options.append(f'<option value="{m.id}">{m.nome}</option>')
    return HttpResponse("".join(options), content_type="text/html")

from django.utils.dateparse import parse_datetime
from condominio.models import Condominio

def consulta_salesforce(limit=200):
    sf = sf_connect()
    #fields = ["Id", "CreatedDate", "reda__Property__c",
    #          "reda__Visitor_Name__c", "reda__Access_Type__c",
    #          "reda__Result__c", "reda__Permitted_Till_Datetime__c"]
    fields = ["reda__Guest_Name__c"]
    where_clause = build_where_clause(None)  # pode ajustar filtros depois
    recs = query_chunk(sf, SOBJECT, fields, where_clause, limit)
    for r in recs:
        r.pop("attributes", None)
    return recs


from django.shortcuts import render
from django.utils.dateparse import parse_datetime
from integrations.allvisitorlogs import sf_connect

@login_required
def visitantes_preaprovados(request):
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

    # Remove metadados e formata datas
    for r in recs:
        r.pop("attributes", None)
        for field in ["CreatedDate", "reda__Permitted_Till_Datetime__c"]:
            val = r.get(field)
            if isinstance(val, str):
                if len(val) > 5 and (val.endswith("+0000") or val.endswith("-0000") or val[-5:].isdigit()):
                    val = val[:-2] + ":" + val[-2:]
                dt = parse_datetime(val)
                if dt:
                    r[field] = dt.strftime("%d/%m/%Y %H:%M")
                else:
                    r[field] = val
            else:
                r[field] = "—"

    # 🔑 Filtro de condomínio
    allowed = allowed_condominios_for(request.user)
    allowed_sf_ids = list(Condominio.objects.filter(id__in=allowed)
                          .values_list("sf_property_id", flat=True))

    if not (request.user.is_superuser or request.user.groups.filter(name="Administrador").exists()):
        recs = [r for r in recs if r.get("reda__Property__c") in allowed_sf_ids]

    ctx = {
        "visitantes": recs,
        "condominios": allowed,
        "total": len(recs),
    }
    return render(request, "portaria/visitantes_preaprovados.html", ctx)

from django.http import JsonResponse
from django.utils.dateparse import parse_datetime

def visitantes_preaprovados_api(request):
    sf = sf_connect()
    soql = """
        SELECT Id, reda__Active_Lease__c, reda__Region__c, Name 
        FROM reda__Property__c
        where reda__Active_Lease__c != null and reda__Region__c = 'a0sHY000000C1WpYAK'
    """
    recs = sf.query_all(soql).get("records", [])
    oportunidade = []
    for r in recs:
        id_propriedade = r.get("Id", "")
        lease_id = r.get("reda__Active_Lease__c", "")
        #adicionar a propriedade
        condominio_id = r.get("reda__Region__c", "")
        prop_nome = r.get("Name", "")
        condominio = Condominio.objects.get(sf_property_id=condominio_id)
        
        bloco = Bloco.objects.get(condominio=condominio.pk)
        unidade = Unidade.objects.filter(bloco=bloco, numero=prop_nome).first()
        if unidade:
            print(f"Unidade {unidade.numero} já existe.")
        else:
            unidade = Unidade.objects.create(
                bloco = bloco,
                numero = prop_nome,
                andar = "0",
                sf_unidade_id = id_propriedade
            )
            print(f"Unidade criada: {unidade}")

            nsoql = f"""
                        SELECT Id, Name
                        FROM Opportunity
                        where Id = '{lease_id}'
                    """
            oportunidade = sf.query_all(nsoql).get("records", [])
            print(f"Oportunidade: {oportunidade}")

            csoql = f"""
                        SELECT Id, ContactId
                        from OpportunityContactRole
                        where OpportunityId = '{lease_id}'
                    """
            contatos = sf.query_all(csoql).get("records", [])
            print(f"Contatos: {contatos}")

            for contato in contatos:
                contact_id = contato.get("ContactId", "")
                print(f"ContactId: {contact_id}")
                ctoql = f"""
                            SELECT Id, Name
                            from Contact
                            where Id = '{contact_id}'
                    """
                contato_detalhes = sf.query_all(ctoql).get("records", [])
                for detalhe in contato_detalhes:
                    nome = detalhe.get("Name", "")
                    print(f"Nome: {nome}")
                    morador = Morador.objects.create(
                        nome = nome,
                        documento = detalhe.get("CCpfTxt__c", ""),
                        unidade = unidade,
                        sf_contact_id = contact_id,
                        sf_opportunity_id = lease_id
                    )
                    print(f"Morador criado: {morador}")

    return JsonResponse({
        "visitantes": recs,
        "leases": lease_id,
        "oportunidade": oportunidade,
    }, safe=False, json_dumps_params={"ensure_ascii": False})

@login_required
def visitantes_preaprovados(request):
    sf = sf_connect()
    condominio = request.GET.get("condominio", "").strip()
    soql = """
        SELECT Id,
               reda__Contact__r.Name,
               reda__Guest_Name__c,
               reda__Property__c,
               reda__Property__r.Name,
               reda__Guest_Phone__c,
               CreatedDate,
               reda__Permitted_Till_Datetime__c,
               reda__Opportunity__r.reda__Region__c
        FROM reda__Visitor_Log__c
        WHERE reda__Permitted_Till_Datetime__c != null
    """

    if condominio:
        sf_property_id = Condominio.objects.filter(id=condominio).values_list("sf_property_id", flat=True).first()
        if sf_property_id:
            soql += f" and reda__Opportunity__r.reda__Region__c = '{sf_property_id}'"   

    soql += f"ORDER BY CreatedDate DESC"

    print(f"SOQL final: {soql}")
            
    recs = sf.query_all(soql).get("records", [])

    # Remove metadados e formata datas
    for r in recs:
        r.pop("attributes", None)
        for field in ["CreatedDate", "reda__Permitted_Till_Datetime__c"]:
            val = r.get(field)
            if isinstance(val, str):
                if len(val) > 5 and (val.endswith("+0000") or val.endswith("-0000") or val[-5:].isdigit()):
                    val = val[:-2] + ":" + val[-2:]
                dt = parse_datetime(val)
                if dt:
                    r[field] = dt.strftime("%d/%m/%Y %H:%M")
                else:
                    r[field] = val
            else:
                r[field] = "—"

    # 🔑 Filtro de condomínio
    allowed = allowed_condominios_for(request.user)
    allowed_sf_ids = list(Condominio.objects.filter(id__in=allowed)
                          .values_list("sf_property_id", flat=True))

    if not (request.user.is_superuser or request.user.groups.filter(name="Administrador").exists()):
        recs = [r for r in recs if r.get("reda__Property__c") in allowed_sf_ids]

    ctx = {
        "visitantes": recs,
        "condominios": allowed,
        "total": len(recs),
    }
    return render(request, "portaria/visitantes_preaprovados.html", ctx)


@login_required
def veiculo_list(request):
    # recupera os condomínios permitidos
    allowed = allowed_condominios_for(request.user)

    qs = Veiculo.objects.select_related("condominio", "unidade", "proprietario").filter(
        condominio__in=allowed
    )

    # Captura valor do filtro
    placa_q = request.GET.get("placa")

    if placa_q:
        qs = qs.filter(placa__icontains=placa_q)

    qs = qs.order_by("placa")

    ctx = {
        "veiculos": qs,
        "condominios": allowed,  # caso queira exibir filtro por condomínio também
        "q": {
            "placa": placa_q or "",
        },
        "total": qs.count(),
    }
    return render(request, "portaria/veiculo_list.html", ctx)

@login_required
#@permission_required("portaria.pode_gerenciar_veiculos")
def veiculo_create(request):
    if request.method == "POST":
        form = VeiculoForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("veiculo_list")
    else:
        form = VeiculoForm()
    return render(request, "portaria/veiculo_form.html", {"form": form})

def get_all_fields(request):
    """Função utilitária para pegar todos os campos de um objeto Salesforce"""
    sf = sf_connect()
    object_name = "reda__Visitor_Log__c"
    limit = 200
    metadata = sf.restful(f"sobjects/{object_name}/describe")
    fields = [f["name"] for f in metadata["fields"]]

    soql = f"SELECT {', '.join(fields)} FROM {object_name} LIMIT {limit}"
    print(f"Executando SOQL:\n{soql}\n")

    records = sf.query_all(soql)["records"]

    for r in records:
        r.pop("attributes", None)
    # ✅ Retorna JSON sem filtro

    return JsonResponse({
        "campos": records,
    }, safe=False, json_dumps_params={"ensure_ascii": False})

def get_property_id(r):
    try:
        return r["reda__Opportunity__r"]["reda__Region__r"]["Id"]
    except (KeyError, TypeError):
        return None

@login_required
def veiculos_unidades(request):
    sf = sf_connect()

    placa = request.GET.get("placa", "").strip()
    condominio_pk = request.GET.get("condominio")

    # 🔑 Condominios permitidos
    allowed = allowed_condominios_for(request.user)

    # Se só tiver 1 condomínio permitido e nenhum filtro informado → pré-seleciona
    if allowed.count() == 1 and not condominio_pk:
        condominio_pk = str(allowed.first().id)

    # Converte o condominio_pk para o ID do Salesforce
    sf_id = None
    if condominio_pk:
        try:
            sf_id = Condominio.objects.get(pk=condominio_pk).sf_property_id
        except Condominio.DoesNotExist:
            sf_id = None

    # Monta a query SOQL
    soql = """
        SELECT Id,
               Name,
               Brand__c,
               reda__Model__c,
               Type__c,
               reda__Color__c,
               reda__Opportunity__c,
               reda__Opportunity__r.reda__Region__c
        FROM reda__Vehicle__c
    """

    where_clauses = []
    if placa:
        where_clauses.append(f"Name LIKE '%{placa}%'")
    if sf_id:
        where_clauses.append(f"reda__Opportunity__r.reda__Region__c = '{sf_id}'")

    if where_clauses:
        soql += " WHERE " + " AND ".join(where_clauses)

    recs = sf.query_all(soql).get("records", [])

    for r in recs:
        r.pop("attributes", None)
        opp = r.get("reda__Opportunity__r") or {}
        r["PropertyId"] = opp.get("reda__Region__c")

    ctx = {
        "veiculos": recs,
        "condominios": allowed,
        "total": len(recs),
        "placa": placa,
        "condominio_pk": condominio_pk,  # 🔑 manda pro template saber qual option marcar
    }
    return render(request, "portaria/veiculos_unidades.html", ctx)


@login_required
def reservas_unidades(request):
    sf = sf_connect()

    condominio_pk = request.GET.get("condominio")

    # 🔑 Condominios permitidos
    allowed = allowed_condominios_for(request.user)

    # Se só tiver 1 condomínio permitido e nenhum filtro informado → pré-seleciona
    if allowed.count() == 1 and not condominio_pk:
        condominio_pk = str(allowed.first().id)

    # Converte o condominio_pk para o ID do Salesforce
    sf_id = None
    if condominio_pk:
        try:
            sf_id = Condominio.objects.get(pk=condominio_pk).sf_property_id
        except Condominio.DoesNotExist:
            sf_id = None

    # Monta a query SOQL
    soql = """
        SELECT Id,
               reda__Property__r.Name,
               reda__Description__c,
               Contact__r.Name,
               reda__Start_Datetime__c,
               reda__End_Datetime__c,
               reda__Total_Booking_Amount__c,
               reda__Status__c
        FROM reda__Booking__c
    """
    if sf_id:
        soql += f" WHERE reda__Property__c = '{sf_id}'"

    recs = sf.query_all(soql).get("records", [])

    for r in recs:
        r.pop("attributes", None)

    ctx = {
        "reservas": recs,
        "condominios": allowed,
        "total": len(recs),
        "condominio_pk": condominio_pk,  # 🔑 manda pro template
    }
    return render(request, "portaria/reservas_unidades.html", ctx)


@login_required
def ajax_responsaveis(request, unidade_id):
    moradores = Morador.objects.filter(unidade_id=unidade_id, ativo=True).order_by("nome")
    options = ['<option value="">—</option>']
    for m in moradores:
        options.append(f'<option value="{m.id}">{m.nome}</option>')
    return HttpResponse("\n".join(options))