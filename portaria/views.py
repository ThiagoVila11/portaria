from django.contrib.auth.decorators import login_required, permission_required
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from portaria.permissions import allowed_condominios_for
from django.utils import timezone
from .models import Encomenda, EventoAcesso, StatusEncomenda, TipoPessoa, MetodoAcesso, ResultadoAcesso, Veiculo
from condominio.models import Condominio, Unidade, Morador
from portaria.models import EventoAcesso, Encomenda
from condominio.models import Condominio, Unidade
from django.utils.dateparse import parse_date
from django.contrib import messages
from portaria.forms import EncomendaForm, EventoAcessoForm
from integrations.sf_tickets import sync_encomenda_to_salesforce
from integrations.visitor import get_salesforce_connection, criar_visitor_log_salesforce
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest
from datetime import date
from integrations.allvisitorlogs import sf_connect, get_all_fields, build_where_clause, query_chunk, SOBJECT
from .forms import VeiculoForm

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
#@permission_required("portaria.pode_registrar_encomenda", raise_exception=True)
def encomenda_create(request):
    if request.method == "POST":
        form = EncomendaForm(request.POST, request.FILES, user=request.user, is_create=True)
        if form.is_valid():
            encomenda = form.save(commit=False)
            encomenda.status = "RECEBIDA"
            encomenda.recebido_por = request.user
            if not encomenda.data_recebimento:
                encomenda.data_recebimento = timezone.now()
            encomenda.save()
            form.save_m2m()

            def _after_commit():
                try:
                    ticket_id = sync_encomenda_to_salesforce(encomenda)
                    if ticket_id:
                        Encomenda.objects.filter(pk=encomenda.pk).update(salesforce_ticket_id=ticket_id)
                        messages.info(request, f"Ticket criado no Salesforce: {ticket_id}")
                except Exception:
                    messages.warning(request, "Encomenda salva, mas houve erro ao integrar com o Salesforce.")
            transaction.on_commit(_after_commit)

            messages.success(request, f"Encomenda {encomenda.pk} criada com sucesso.")
            return redirect("encomenda_list")
    else:
        form = EncomendaForm(user=request.user, is_create=True)

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
        return redirect('encomenda_list')
    return render(request, 'portaria/encomenda_entregar_confirm.html', {'encomenda': enc})


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
            try:
                sf = get_salesforce_connection() 
                criar_visitor_log_salesforce(
                    sf=sf,
                    property_id= acesso.unidade.sf_unidade_id,  #acesso.condominio.sf_property_id,
                    host_contact_id=None,
                    visitante_nome=acesso.pessoa_nome,
                    visitante_endereco=str(acesso.unidade) if acesso.unidade else "",
                    visitante_telefone=acesso.documento,
                    visitante_email=""
                )
                messages.success(request, "Acesso registrado e enviado ao Salesforce.")
            except Exception as e:
                messages.error(request, f"Acesso salvo, mas falhou integração SF: {e}")

            return redirect("acesso_list")
    else:
        form = EventoAcessoForm(user=request.user)

    return render(request, "portaria/acesso_form.html", {"form": form})


@login_required
#@permission_required('portaria.delete_encomenda', raise_exception=True)
@require_POST
def encomenda_delete(request, pk):
    # só permite excluir encomendas de condomínios que o usuário pode ver
    allowed = allowed_condominios_for(request.user)
    encomenda = get_object_or_404(Encomenda, pk=pk, condominio__in=allowed)

    encomenda.delete()
    messages.success(request, f'Encomenda #{pk} excluída com sucesso.')
    return redirect('encomenda_list')

@login_required
#@permission_required('portaria.delete_eventoacesso', raise_exception=True)
@require_POST
def acesso_delete(request, pk):
    allowed = allowed_condominios_for(request.user)
    evento = get_object_or_404(EventoAcesso, pk=pk, condominio__in=allowed)
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

from django.shortcuts import render
from django.utils.dateparse import parse_datetime
from integrations.allvisitorlogs import sf_connect

def visitantes_preaprovados(request):
    sf = sf_connect()
    soql = """
        SELECT Id,
               reda__Contact__r.Name,
               reda__Guest_Name__c,
               reda__Property__c,
               reda__Guest_Phone__c,
               CreatedDate,
               reda__Permitted_Till_Datetime__c,
               reda__Property__r.Name

        FROM reda__Visitor_Log__c
        WHERE reda__Permitted_Till_Datetime__c != null
        ORDER BY CreatedDate DESC
        LIMIT 500
    """
    recs = sf.query_all(soql).get("records", [])

    for r in recs:
        r.pop("attributes", None)

        # formata datas com segurança
        for field in ["CreatedDate", "reda__Permitted_Till_Datetime__c"]:
            val = r.get(field)
            if isinstance(val, str):
                # normaliza timezone ex.: +0000 → +00:00
                if len(val) > 5 and (val.endswith("+0000") or val.endswith("-0000") or val[-5:].isdigit()):
                    val = val[:-2] + ":" + val[-2:]
                dt = parse_datetime(val)
                if dt:
                    r[field] = dt #.strftime("%d/%m/%Y %H:%M")
                else:
                    r[field] = val  # fallback: mostra original
            else:
                r[field] = "—"

    ctx = {
        "visitantes": recs,
        "total": len(recs),
    }
    return render(request, "portaria/visitantes_preaprovados.html", ctx)

@login_required
def veiculo_list(request):
    veiculos = Veiculo.objects.select_related("condominio", "unidade", "proprietario")
    return render(request, "portaria/veiculo_list.html", {"veiculos": veiculos})

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