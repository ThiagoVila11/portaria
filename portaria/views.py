import base64
import os
from django.contrib.auth.decorators import login_required, permission_required
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from portaria.permissions import allowed_condominios_for
from django.utils import timezone
from .models import Encomenda, EventoAcesso, StatusEncomenda, TipoPessoa, MetodoAcesso, ResultadoAcesso, Veiculo, Condominio
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
from datetime import date, datetime, timezone, timedelta
from integrations.allvisitorlogs import sf_connect, get_all_fields, build_where_clause, query_chunk, SOBJECT
from .forms import VeiculoForm
from django.http import JsonResponse
from collections import OrderedDict
from datetime import datetime
from django.utils import timezone
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q


@login_required
def dashboard(request):
    ctx = {
    'total_encomendas': Encomenda.objects.count(),
    'encomendas_pendentes': Encomenda.objects.filter(status=StatusEncomenda.RECEBIDA).count(),
    'acessos_hoje': EventoAcesso.objects.filter(criado_em__date=timezone.now().date()).count(),
    }
    return render(request, 'portaria/dashboard.html', ctx)


@login_required
def encomenda_list(request):
    sf = sf_connect()
    allowed = allowed_condominios_for(request.user)
    qs = Encomenda.objects.select_related("unidade", "condominio").filter(condominio__in=allowed)

    condominio = request.GET.get("condominio")
    unidade = request.GET.get("unidade")
    dt_ini = request.GET.get("dt_ini")
    dt_fim = request.GET.get("dt_fim")
    destinatario = request.GET.get("destinatario")
    status = request.GET.get("status")

    # 🔹 Se for a primeira carga (sem filtros), define as datas padrão
    if not any([dt_ini, dt_fim, condominio, destinatario, status]):
        hoje = date.today()
        dt_ini = hoje.replace(day=1).isoformat()  # primeiro dia do mês
        dt_fim = hoje.isoformat()                 # data atual

    # 🔹 Filtros
    if condominio:
        qs = qs.filter(condominio_id=condominio)
    if unidade:
        qs = qs.filter(unidade_id=unidade)
    if dt_ini:
        qs = qs.filter(data_recebimento__date__gte=dt_ini)
    if dt_fim:
        qs = qs.filter(data_recebimento__date__lte=dt_fim)
    if destinatario:
        #qs = qs.filter(destinatario__icontains=destinatario)
        qs = qs.filter(destinatario__nome__icontains=destinatario)

    if status:
        qs = qs.filter(status=status)

    qs = qs.order_by("-data_recebimento")

    for e in qs:
        if not e.salesforce_ticket_id:
            continue  # só atualiza se tiver o ID do Visitor Log salvo

    # 🔹 Paginação (20 por página)
    paginator = Paginator(qs, 20)
    page = request.GET.get("page")
    try:
        encomendas = paginator.page(page)
    except PageNotAnInteger:
        encomendas = paginator.page(1)
    except EmptyPage:
        encomendas = paginator.page(paginator.num_pages)

    unidades = Unidade.objects.filter(bloco__condominio__in=allowed).order_by("numero")

    ctx = {
        "encomendas": encomendas,
        "condominios": allowed,
        "unidades": unidades,
        "status_choices": Encomenda._meta.get_field("status").choices,  # compatível com qualquer estrutura
        "q": {
            "condominio": condominio or "",
            "unidade": unidade or "",
            "dt_ini": dt_ini or "",
            "dt_fim": dt_fim or "",
            "destinatario": destinatario or "",
            "status": status or "",
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
        print("Arquivos enviados:", request.FILES)
        print(f"Form valid: {form.is_valid()}")
        if form.is_valid():
            encomenda = form.save(commit=False)
            encomenda.status = "RECEBIDA"
            encomenda.recebido_por = request.user
            if not encomenda.data_recebimento:
                encomenda.data_recebimento = timezone.now()
            encomenda.save()
            print(f"Encomenda antes de salvar: {encomenda}")
            # ✅ Salva os arquivos associados agora
            for i in range(1, 6):
                arquivo = form.cleaned_data.get(f"arquivo_0{i}")
                print(f"Arquivo na tabela encomendas {i}: {arquivo}")
                if arquivo:
                    setattr(encomenda, f"arquivo_0{i}", arquivo)
                    print(f"Salvando arquivo {i} para encomenda {encomenda.id}")

            encomenda.save() 
            print(f"Encomenda {encomenda.id} salva com sucesso.")
            print(f"id do salesforce_ticket_id antes da integração: {encomenda.salesforce_ticket_id}")
            # 🔑 só sincroniza se ainda não estiver integrado
            if not encomenda.salesforce_ticket_id:
                print("Tentando integrar com Salesforce...")
                try:
                    resultado = sync_encomenda_to_salesforce(encomenda)
                    print(f"Resultado da integração com Salesforce: {resultado}")
                    ticket_id = resultado["id"]
                    print("Ticket ID retornado:", ticket_id)
                    senha = resultado["senha"]
                    print("Senha retornada:", senha)
                    if ticket_id:
                        encomenda.salesforce_ticket_id = ticket_id

                        # Consulta SOQL no Salesforce
                        sf = sf_connect()
                        soql = f"""
                            SELECT Id, Password__c
                            FROM reda__Ticket__c
                            WHERE Id = '{ticket_id}'
                            and Password__c != null
                        """
                        res_senha = sf.query(soql).get("records", [])
                        SenhaRetirada = res_senha[0].get("Password__c")
                        encomenda.SenhaRetirada = SenhaRetirada
                        print(f"Salvando ticket_id {ticket_id} e senha {SenhaRetirada} na encomenda {encomenda.id}")
                        #encomenda.save(update_fields=["salesforce_ticket_id"])
                        encomenda.save(update_fields=["salesforce_ticket_id", "SenhaRetirada"])
                        messages.info(request, f"Ticket criado no Salesforce: {ticket_id}")
                except Exception:
                    messages.warning(request, "Encomenda salva, mas houve erro ao integrar com o Salesforce.")
            else:
                ticket_id = encomenda.salesforce_ticket_id
                print("Ticket ID retornado:", ticket_id)
                if ticket_id:
                        # Consulta SOQL no Salesforce
                        sf = sf_connect()
                        soql = f"""
                            SELECT Id, Password__c
                            FROM reda__Ticket__c
                            WHERE Id = '{ticket_id}'
                            and Password__c != null
                        """
                        res_senha = sf.query(soql).get("records", [])
                        SenhaRetirada = res_senha[0].get("Password__c")
                        encomenda.SenhaRetirada = SenhaRetirada
                        print(f"Salvando ticket_id {ticket_id} e senha {SenhaRetirada} na encomenda {encomenda.id}")
                        encomenda.save(update_fields=["salesforce_ticket_id", "SenhaRetirada"])
                        messages.info(request, f"Ticket criado no Salesforce: {ticket_id}")
                messages.info(request, f"Ticket criado no Salesforce: {encomenda.salesforce_ticket_id} (Senha: {encomenda.SenhaRetirada})")

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
        retirado_por = request.POST.get("retirado_por", "").strip()
        print("Retirado por:", retirado_por)
        enc.status = StatusEncomenda.ENTREGUE
        enc.data_entrega = timezone.now()
        enc.entregue_por = request.user
        enc.RetiradoPor = retirado_por
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
    # 🔹 Conecta ao Salesforce
    sf = sf_connect()

    # 🔹 Busca todos os acessos locais
    eventos = EventoAcesso.objects.all().select_related("unidade", "condominio")

    # 🔹 Atualiza status com o Salesforce
    for evento in eventos:
        if not evento.sf_visitor_log_id:
            continue  # só atualiza se tiver o ID do Visitor Log salvo

        try:
            # Consulta SOQL no Salesforce
            soql = f"""
                SELECT Id, reda__Status__c, reda__Permitted_Till_Datetime__c
                FROM reda__Visitor_Log__c
                WHERE Id = '{evento.sf_visitor_log_id}'
            """
            result = sf.query(soql).get("records", [])
            print(f"Consulta SOQL para {evento.pessoa_nome} (ID {evento.sf_visitor_log_id}): {result}")
            if result:
                status_sf = result[0].get("reda__Status__c")
                permitted_str = result[0].get("reda__Permitted_Till_Datetime__c")

                # Traduz status Salesforce → local
                STATUS_MAP = {
                    "Permitido": "Permitted",
                    "Negado": "Cancelled",
                    "Aguardando": "Requested",
                    "Liberado": "Checked In",
                }
                novo_status = STATUS_MAP.get(status_sf, evento.resultado)
                # 🔹 Atualiza o campo "liberado_ate" se houver valor
                if permitted_str:
                    try:
                        permitted_dt = datetime.fromisoformat(permitted_str.replace("Z", "+00:00"))
                        evento.liberado_ate = permitted_dt
                    except Exception as e:
                        print(f"⚠️ Erro ao converter data de liberação ({permitted_str}): {e}")

                print(f"Status Salesforce: {status_sf} → Novo status local: {novo_status}")
                #if novo_status != evento.resultado:
                #evento.resultado = status_sf
                #evento.save(update_fields=["resultado"])

                # 🔹 Atualiza se houver mudanças
                campos_para_salvar = []
                #if novo_status != evento.resultado:
                evento.resultado = status_sf
                campos_para_salvar.append("resultado")
                #if permitted_str:
                campos_para_salvar.append("liberado_ate")

                if campos_para_salvar:
                    evento.save(update_fields=campos_para_salvar)
                    print(f"✅ Atualizado {evento.pessoa_nome}: {status_sf} até {evento.liberado_ate}")

        except Exception as e:
            print(f"⚠️ Erro ao atualizar {evento.pessoa_nome}: {e}")

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

# 🔹 Paginação — 20 por página
    paginator = Paginator(qs, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    ctx = {
        "eventos": page_obj, #qs,
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
            acesso.criado_por = request.user

            try:
                # 🔹 Conexão Salesforce
                sf = get_salesforce_connection()
                telefone = acesso.pessoa_telefone.strip()
                oportunidade_id = acesso.responsavel.sf_opportunity_id if acesso.responsavel else None

                # ⚙️ Verifica se já há Visitor_Log ativo no Salesforce
                if telefone and oportunidade_id:
                    soql = f"""
                        SELECT Id, reda__Permitted_Till_Datetime__c
                        FROM reda__Visitor_Log__c
                        WHERE reda__Opportunity__c = '{oportunidade_id}'
                        AND reda__Guest_Phone__c = '{telefone}'
                        AND reda__Permitted_Till_Datetime__c != null
                        AND reda__Status__c = 'Permitted'
                        ORDER BY reda__Permitted_Till_Datetime__c DESC
                        LIMIT 1
                    """
                    print(soql)
                    result = sf.query(soql).get("records", [])
                    print(f"Resultado da consulta de pré-liberação: {result}")
                    if result:
                        #permitted_str = result[0].get("reda__Permitted_Till_Datetime__c")
                        #permitted_till = datetime.fromisoformat(permitted_str.replace("Z", "+00:00"))
                        #data_salesforce = datetime.strptime(permitted_str, "%Y-%m-%dT%H:%M:%S.%f%z")
                        #permitted_till = datetime.strptime(permitted_str, "%d/%m/%Y - %H:%M") #parse_salesforce_datetime(result[0].get("reda__Permitted_Till_Datetime__c"))
                        permitted_str = result[0].get("reda__Permitted_Till_Datetime__c")
                        permitted_till = parse_salesforce_datetime_utc(permitted_str)
                        now_utc = timezone.now()                    
                        print(f"Permitted till: {permitted_till}, Now UTC: {now_utc}")
                        if permitted_till  > now_utc:
                            status_resultado = "Permitted"
                            acesso.resultado = "Permitted"  # 🔹 Liberado automaticamente
                            acesso.liberado_ate = permitted_till
                            #messages.info(
                            #    request,
                            #    f"Visitante já pré-aprovado no Salesforce.",
                            #)

            except Exception as e:
                print(f"⚠️ Erro ao verificar pré-liberação no Salesforce: {e}")

            # 🔹 Salva o registro local
            acesso.save()

            # 🔹 Cria o VisitorLog no Salesforce (se não existir ainda)
            if not acesso.sf_visitor_log_id:
                try:
                    print("Tentando criar VisitorLog no Salesforce...")
                    visitor_log_id = criar_visitor_log_salesforce(
                        sf=sf,
                        propriedade_id=acesso.unidade.sf_unidade_id if acesso.unidade else "",
                        oportunidade_id=acesso.responsavel.sf_opportunity_id if acesso.responsavel else "",
                        contato_id=acesso.responsavel.sf_contact_id if acesso.responsavel else "",
                        resultado=acesso.resultado,
                        visitante_nome=acesso.pessoa_nome,
                        visitante_endereco=str(acesso.unidade) if acesso.unidade else "",
                        visitante_telefone=acesso.pessoa_telefone,
                        visitante_email="",
                        visitante_tipo=acesso.pessoa_tipo,
                    )

                    if visitor_log_id and "id" in visitor_log_id:
                        acesso.sf_visitor_log_id = visitor_log_id["id"]
                        acesso.save(update_fields=["sf_visitor_log_id"])
                        messages.success(request, f"Visitor Log criado no Salesforce: {visitor_log_id['id']}")
                    else:
                        messages.warning(request, "Acesso salvo, mas Salesforce não retornou um ID válido.")

                except Exception as e:
                    messages.error(request, f"Acesso salvo, mas falhou integração com Salesforce: {e}")

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

from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from .models import Unidade

@login_required
def ajax_unidades_por_condominio(request, condominio_id: int):
    #unidades = (
    #    Unidade.objects
    #    .filter(bloco__condominio_id=condominio_id)
    #    .filter(numero__iregex=r"[0-9]{4}$")  # 🔍 Apenas se termina com 4 dígitos numéricos
    #    .select_related("bloco")
    #    .order_by("bloco__nome", "numero")
    #)
    unidades = (
        Unidade.objects
        .filter(
            Q(bloco__condominio_id=condominio_id),
            Q(numero__iregex=r"[0-9]{4}$") | Q(numero__icontains="recepção")
        )
        .select_related("bloco")
        .order_by("bloco__nome", "numero")
    )

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

from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage


@login_required
def visitantes_preaprovados(request):
    print("Acessando visitantes_preaprovados")
    sf = sf_connect()

    # 🧭 Filtro
    condominio_raw = request.GET.get("condominio", "").strip()
    condominio = int(condominio_raw) if condominio_raw.isdigit() else None
    sf_cursor = request.GET.get("sf_page")  # 🔹 novo: cursor Salesforce

    allowed = allowed_condominios_for(request.user)
    allowed_sf_ids = list(
        Condominio.objects.filter(id__in=allowed).values_list("sf_property_id", flat=True)
    )

    # 🧱 Monta SOQL base
    soql = """
        SELECT Id,
               reda__Contact__r.Name,
               reda__Guest_Name__c,
               reda__Property__r.Name,
               reda__Guest_Phone__c,
               CreatedDate,
               reda__Permitted_Till_Datetime__c
        FROM reda__Visitor_Log__c
        WHERE reda__Permitted_Till_Datetime__c != null
    """

    # 🧭 Aplica filtro de condomínio
    if condominio:
        sf_property_id = (
            Condominio.objects.filter(id=condominio)
            .values_list("sf_property_id", flat=True)
            .first()
        )
        if sf_property_id:
            soql += f" AND reda__Property__c = '{sf_property_id}'"

    soql += "LIMIT 500"
    soql += " ORDER BY CreatedDate DESC"

    # 🧭 Pega página do Salesforce
    if sf_cursor:
        print(f"🔁 Buscando próxima página via cursor: {sf_cursor}")
        result = sf.query_more(sf_cursor, True)
    else:
        print(f"📡 Primeira consulta Salesforce: {soql}")
        result = sf.query(soql)

    recs = result.get("records", [])
    next_cursor = result.get("nextRecordsUrl")  # se houver próxima página
    print(f"📦 Registros retornados: {len(recs)} | Próxima página: {bool(next_cursor)}")

    # 🔹 Formata datas
    for r in recs:
        r.pop("attributes", None)
        for field in ["CreatedDate", "reda__Permitted_Till_Datetime__c"]:
            val = r.get(field)
            if val and "T" in val:
                val = val.replace("T", " ").split(".")[0]
                r[field] = val
            else:
                r[field] = "—"

    # 🔹 Contexto
    ctx = {
        "visitantes": recs,
        "next_cursor": next_cursor,
        "prev_cursor": sf_cursor,  # não real, mas útil pra controle
        "condominios": allowed,
        "total": result.get("totalSize", len(recs)),
        "condominio_pk": condominio_raw,
    }

    return render(request, "portaria/visitantes_preaprovados.html", ctx)



from django.http import JsonResponse
from django.utils.dateparse import parse_datetime

#@csrf_exempt  # permite chamadas externas (ex: Postman)
def visitantes_preaprovados_api(request):
    """
    API que sincroniza propriedades, unidades e moradores
    do Salesforce com o banco local.
    """
    if request.method not in ["GET", "POST"]:
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    try:
        sf = sf_connect()

        soql = """
            SELECT Id, reda__Active_Lease__c, reda__Region__c, Name
            FROM reda__Property__c
        """
        #WHERE reda__Active_Lease__c != null
        recs = sf.query_all(soql).get("records", [])
        resultado = []

        for r in recs:
            id_propriedade = r.get("Id", "")
            lease_id = r.get("reda__Active_Lease__c", "")
            condominio_id = r.get("reda__Region__c", "")
            prop_nome = r.get("Name", "")

            try:
                condominio = Condominio.objects.get(sf_property_id=condominio_id)
            except Condominio.DoesNotExist:
                print(f"⚠️ Condomínio não encontrado: {condominio_id}")
                continue

            bloco = Bloco.objects.filter(condominio=condominio.pk).first()
            if not bloco:
                print(f"⚠️ Nenhum bloco encontrado para {condominio.nome}")
                continue

            unidade = Unidade.objects.filter(bloco=bloco, numero=prop_nome).first()
            if unidade:
                print(f"Unidade {unidade.numero} já existe.")
            else:
                unidade = Unidade.objects.create(
                    bloco=bloco,
                    numero=prop_nome,
                    andar="0",
                    sf_unidade_id=id_propriedade,
                )
                print(f"✅ Unidade criada: {unidade}")
                # Sincroniza moradores vinculados à lease
                if lease_id:            
                    nsoql = f"""
                        SELECT Id, Name
                        FROM Opportunity
                        WHERE Id = '{lease_id}'
                    """
                    oportunidade = sf.query_all(nsoql).get("records", [])

                    csoql = f"""
                        SELECT Id, ContactId
                        FROM OpportunityContactRole
                        WHERE OpportunityId = '{lease_id}'
                    """
                    contatos = sf.query_all(csoql).get("records", [])

                    for contato in contatos:
                        contact_id = contato.get("ContactId", "")
                        ctoql = f"""
                            SELECT Id, Name, CCpfTxt__c
                            FROM Contact
                            WHERE Id = '{contact_id}'
                        """
                        contato_detalhes = sf.query_all(ctoql).get("records", [])

                        for detalhe in contato_detalhes:
                            nome = detalhe.get("Name", "")
                            morador = Morador.objects.create(
                                nome=nome,
                                documento=detalhe.get("CCpfTxt__c", ""),
                                unidade=unidade,
                                sf_contact_id=contact_id,
                                sf_opportunity_id=lease_id,
                            )
                            print(f"👤 Morador criado: {morador}")

            resultado.append({
                "propriedade": prop_nome,
                "lease_id": lease_id,
                "condominio": condominio.nome,
                "unidade": unidade.numero if unidade else None,
            })

        return JsonResponse({
            "status": "sucesso",
            "total_processado": len(resultado),
            "detalhes": resultado,
        }, status=200, json_dumps_params={"ensure_ascii": False, "indent": 2})

    except Exception as e:
        print(f"❌ Erro na sincronização: {e}")
        return JsonResponse({"erro": str(e)}, status=500)


from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

@login_required
def visitantes_preaprovados(request):
    sf = sf_connect()

    condominio_param = request.GET.get("condominio", "").strip()
    unidade_filtro = request.GET.get("unidade", "").strip()
    print(f"🔍 Filtros recebidos - Condomínio: '{condominio_param}', Unidade: '{unidade_filtro}'")


    # 🔹 Busca os condomínios permitidos ao usuário
    allowed = allowed_condominios_for(request.user)
    allowed_sf_ids = list(
        Condominio.objects.filter(id__in=allowed)
        .values_list("sf_property_id", flat=True)
    )

    print(f"✅ Condomínios permitidos (SF IDs): {allowed_sf_ids}")

    # 🔹 Monta o SOQL base
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
    """

    # 🔹 Filtro manual (condomínio selecionado)
    if condominio_param:
        sf_property_id = (
            Condominio.objects.filter(id=condominio_param)
            .values_list("sf_property_id", flat=True)
            .first()
        )
        if sf_property_id:
            soql += f" AND reda__Property__c = '{sf_property_id}'"
            print(f"🧩 Filtro manual aplicado: reda__Property__c = '{sf_property_id}'")
    # 🔹 Filtro automático (usuário com condomínios permitidos)
    elif allowed_sf_ids:
        sf_filter = ",".join(f"'{c}'" for c in allowed_sf_ids if c)
        #soql += f" AND reda__Property__c IN ({sf_filter})"
        print(f"🔒 Filtro automático aplicado: reda__Property__c IN ({sf_filter})")

    if unidade_filtro:    
        unidade_desc = Unidade.objects.filter(id=unidade_filtro).first()
        unidade_desc = 'VMD-0502'
        print(f"🔍 Unidade filtro descrição: '{unidade_desc}'")
        soql += f" AND reda__Property__r.Name = '{unidade_desc}'"

    # 🔹 Ordenação
    soql += " ORDER BY CreatedDate DESC"

    print(f"📡 Executando consulta Salesforce:\n{soql}")
    result = sf.query_all(soql)

    recs = result.get("records", [])
    print(f"📦 Registros retornados: {len(recs)}")

    # 🔹 Formata datas
    for r in recs:
        r.pop("attributes", None)
        print(f"Nome: {r.get('reda__Property__r.Name')}")
        for field in ["CreatedDate", "reda__Permitted_Till_Datetime__c"]:
            val = r.get(field)
            if isinstance(val, str) and "T" in val:
                val = val.replace("T", " ").split(".")[0]
                r[field] = val
            else:
                r[field] = "—"

    # 🔹 Paginação local — 5 registros por página
    paginator = Paginator(recs, 20)
    page_number = request.GET.get("page")

    try:
        visitantes = paginator.page(page_number)
    except PageNotAnInteger:
        visitantes = paginator.page(1)
    except EmptyPage:
        visitantes = paginator.page(paginator.num_pages)

    ctx = {
        "visitantes": visitantes,
        "condominios": allowed,
        "total": len(recs),
        "condominio_pk": condominio_param,
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
               reda__Opportunity__r.reda__Region__c, 
               reda__Opportunity__r.reda__Property__r.Name,
               Vehicle_Unit__c
        FROM reda__Vehicle__c
    """

    where_clauses = []
    where_clauses.append(f"reda__Opportunity__r.reda__Property__r.Name like '%VAG%'")
    if placa:
        where_clauses.append(f"Name LIKE '%{placa}%'")
    if sf_id:
        where_clauses.append(f"reda__Opportunity__r.reda__Region__c = '{sf_id}'")

    if where_clauses:
        soql += " WHERE " + " AND ".join(where_clauses)

    recs = sf.query_all(soql).get("records", [])
    TIPO_TRADUZIDO = {
        "Car": "Carro",
        "Motorcycle": "Motocicleta",
        "Truck": "Caminhão",
        "Bicycle": "Bicicleta",
        "Scooter": "Scooter",
        "Van": "Van",
}
    for r in recs:
        r.pop("attributes", None)
        opp = r.get("reda__Opportunity__r") or {}
        r["PropertyId"] = opp.get("reda__Region__c")
        tipo = r.get("Type__c")
        r["Tipo_PT"] = TIPO_TRADUZIDO.get(tipo, tipo)

    # 🔹 Paginação (20 por página)
    paginator = Paginator(recs, 20)
    page = request.GET.get("page")
    try:
        veiculos_lista = paginator.page(page)
    except PageNotAnInteger:
        veiculos_lista = paginator.page(1)
    except EmptyPage:
        veiculos_lista = paginator.page(paginator.num_pages)

    ctx = {
        "veiculos": veiculos_lista,
        "condominios": allowed,
        "total": len(recs),
        "placa": placa,
        "condominio_pk": condominio_pk,  # 🔑 manda pro template saber qual option marcar
    }
    return render(request, "portaria/veiculos_unidades.html", ctx)

@login_required
def morador_unidades(request):
    # 🔹 Parâmetros de filtro
    morador_nome = request.GET.get("morador", "").strip()
    print(f"🔍 Filtro morador: '{morador_nome}'")
    apto = request.GET.get("apto", "").strip()
    print(f"🔍 Filtro apto: '{apto}'")
    condominio_pk = request.GET.get("condominio")
    print(f"🔍 Filtro condomínio: '{condominio_pk}'")

    # 🔹 Condominios permitidos
    allowed = allowed_condominios_for(request.user)

    # Se o usuário tiver só 1 condomínio permitido → seleciona automaticamente
    if allowed.count() == 1 and not condominio_pk:
        condominio_pk = str(allowed.first().id)

    # 🔹 Base Query
    qs = (
        Morador.objects
        .select_related("unidade", "unidade__bloco", "unidade__bloco__condominio")
        .filter(unidade__bloco__condominio__in=allowed)
    )

    # 🔹 Filtros
    qs = qs.filter(ativo=True)  # só ativos
    if condominio_pk:
        qs = qs.filter(unidade__bloco__condominio_id=condominio_pk)

    if morador_nome:
        qs = qs.filter(nome__icontains=morador_nome)

    if apto:
        qs = qs.filter(unidade__numero__icontains=apto)

    # 🔹 Ordenação por apartamento e nome
    qs = qs.order_by("unidade__bloco__nome", "unidade__numero", "nome")

    # 🔹 Monta resultado formatado
    moradores = [
        {
            "Nome": m.nome,
            "Apto": m.unidade.numero if m.unidade else "—",
            "Bloco": m.unidade.bloco.nome if m.unidade and m.unidade.bloco else "—",
            "Condominio": m.unidade.bloco.condominio.nome if m.unidade and m.unidade.bloco else "—",
            "sf_contact_id": m.sf_contact_id or "",
            "sf_opportunity_id": m.sf_opportunity_id or "",
        }
        for m in qs
    ]

    # 🔹 Paginação (20 por página)
    paginator = Paginator(moradores, 20)
    page = request.GET.get("page")
    try:
        moradores_lista = paginator.page(page)
    except PageNotAnInteger:
        moradores_lista = paginator.page(1)
    except EmptyPage:
        moradores_lista = paginator.page(paginator.num_pages)

    ctx = {
        "moradores": moradores_lista,
        "condominios": allowed,
        "total": len(moradores),
        "morador": morador_nome,
        "condominio_pk": condominio_pk,
    }

    return render(request, "portaria/morador_list.html", ctx)


@login_required
def reservas_unidades(request):
    sf = sf_connect()

    condominio_pk = request.GET.get("condominio")
    data_inicio = request.GET.get("data_inicio")
    data_fim = request.GET.get("data_fim")

    allowed = allowed_condominios_for(request.user)

    # 🔹 Se o usuário tiver apenas 1 condomínio, já seleciona automaticamente
    if allowed.count() == 1 and not condominio_pk:
        condominio_pk = str(allowed.first().id)

    # 🔹 Busca o ID Salesforce do condomínio
    sf_id = None
    if condominio_pk:
        try:
            sf_id = Condominio.objects.get(pk=condominio_pk).sf_property_id
        except Condominio.DoesNotExist:
            sf_id = None

    # 🔹 Query base
    soql = """
        SELECT Id,
               reda__Property__r.Name,
               reda__Description__c,
               Contact__r.Name,
               reda__Start_Datetime__c,
               reda__End_Datetime__c,
               reda__Total_Booking_Amount__c,
               reda__Status__c,
               reda__Property__r.reda__Region__c,
               reda__Opportunity__r.reda__Property__r.name,
               reda__Opportunity__c,
               Opportunity_property__c
        FROM reda__Booking__c
    """

    where_clauses = []

    if sf_id:
        where_clauses.append(f"reda__Property__r.reda__Region__c = '{sf_id}'")

    # ✅ Datas sem aspas
    if data_inicio:
        try:
            data_inicio_iso = datetime.strptime(data_inicio, "%Y-%m-%d").strftime("%Y-%m-%dT00:00:00Z")
            where_clauses.append(f"reda__Start_Datetime__c >= {data_inicio_iso}")
        except Exception:
            pass

    if data_fim:
        try:
            data_fim_iso = datetime.strptime(data_fim, "%Y-%m-%d").strftime("%Y-%m-%dT23:59:59Z")
            where_clauses.append(f"reda__End_Datetime__c <= {data_fim_iso}")
        except Exception:
            pass

    # 🔹 Monta WHERE se houver filtros
    if where_clauses:
        soql += " WHERE " + " AND ".join(where_clauses)

    soql += " ORDER BY reda__Start_Datetime__c DESC"

    print("SOQL final:", soql)  # 🪶 debug opcional

    recs = sf.query_all(soql).get("records", [])

    STATUS_TRADUZIDO = {
        "Pending": "Pendente",
        "Confirmed": "Confirmada",
        "Cancelled": "Cancelada",
        "Completed": "Concluída",
        "Rejected": "Recusada",
        "In Progress": "Em andamento",
        "Draft": "Rascunho",
    }
    # 🔹 Formata datas legíveis
    for r in recs:
        r.pop("attributes", None)
        #for field in ["reda__Start_Datetime__c", "reda__End_Datetime__c"]:
        status = r.get("reda__Status__c")
        r["Status_PT"] = STATUS_TRADUZIDO.get(status, status)
    # 🕒 Converte strings ISO → datetime
        r["reda__Start_Datetime__c"] = parse_salesforce_datetime(r.get("reda__Start_Datetime__c"))
        r["reda__End_Datetime__c"] = parse_salesforce_datetime(r.get("reda__End_Datetime__c"))

    # 🔹 Paginação (20 por página)
    paginator = Paginator(recs, 20)
    page = request.GET.get("page")
    try:
        reservas_lista = paginator.page(page)
    except PageNotAnInteger:
        reservas_lista = paginator.page(1)
    except EmptyPage:
        reservas_lista = paginator.page(paginator.num_pages)

    ctx = {
        "reservas": reservas_lista,
        "condominios": allowed,
        "total": len(recs),
        "condominio_pk": condominio_pk,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
    }
    return render(request, "portaria/reservas_unidades.html", ctx)

@login_required
def ajax_responsaveis(request, unidade_id):
    moradores = Morador.objects.filter(unidade_id=unidade_id, ativo=True).order_by("nome")
    options = ['<option value="">—</option>']
    for m in moradores:
        options.append(f'<option value="{m.id}">{m.nome}</option>')
    return HttpResponse("\n".join(options))

def parse_salesforce_datetime(dt_str):
    """Converte '2025-10-15T12:00:00.000+0000' → '15/10/2025 - 12:00'"""
    if not dt_str:
        return ""
    try:
        dt = datetime.strptime(dt_str.split('.')[0], "%Y-%m-%dT%H:%M:%S")
        return dt.strftime("%d/%m/%Y - %H:%M")
    except Exception:
        return dt_str
    
from datetime import datetime
from django.utils import timezone

def parse_salesforce_datetime_utc(dt_str):
    """Converte string do Salesforce (ex: 2025-10-31T15:00:00.000+0000) em datetime com timezone UTC"""
    if not dt_str:
        return None
    try:
        # Salesforce envia timezone como +0000 → converte para +00:00
        if dt_str.endswith('+0000'):
            dt_str = dt_str[:-5] + '+00:00'

        # Remove milissegundos, se existirem
        if '.' in dt_str:
            partes = dt_str.split('.')
            if len(partes) > 1:
                dt_str = partes[0] + dt_str[-6:]

        # Converte para datetime
        dt = datetime.fromisoformat(dt_str)
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone=timezone.utc)
            dt = dt + timedelta(hours=3, minutes=30)
        return dt
    except Exception as e:
        print(f"⚠️ Erro ao converter datetime Salesforce: {e} (entrada: {dt_str})")
        return None


def get_all_fields(request):
    """Função utilitária para pegar todos os campos de um objeto Salesforce"""
    sf = sf_connect()
    object_name = "reda__Property__c"
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
    
def anexar_arquivo_salesforce(file_path, opportunity_id, titulo="Anexo"):
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
        "LinkedEntityId": opportunity_id,
        "ShareType": "V",
        "Visibility": "AllUsers",
    }
    sf.ContentDocumentLink.create(link_data)
    print(f"🔗 Arquivo {filename} vinculado à Opportunity {opportunity_id}")


@login_required
def ajax_unidades(request, condominio_id):
    """
    Retorna as <option> de unidades pertencentes ao condomínio informado.
    Usado para popular o filtro dinâmico via AJAX.
    """
    unidades = Unidade.objects.filter(bloco__condominio_id=condominio_id).order_by("numero")

    html = "".join([f'<option value="{u.id}">{u}</option>' for u in unidades])

    return HttpResponse(html)