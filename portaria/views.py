from django.contrib.auth.decorators import login_required, permission_required
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from portaria.permissions import allowed_condominios_for
from django.utils import timezone
from .models import Encomenda, EventoAcesso, StatusEncomenda, TipoPessoa, MetodoAcesso, ResultadoAcesso
from condominio.models import Condominio, Unidade, Morador
from portaria.models import EventoAcesso, Encomenda
from condominio.models import Condominio, Unidade
from django.utils.dateparse import parse_date
from django.contrib import messages


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
    condominio_id = request.GET.get("condominio")       # None se não veio no GET
    dt_ini        = request.GET.get("dt_ini")
    dt_fim        = request.GET.get("dt_fim")
    destinatario_q = request.GET.get("destinatario")

    # Detecta "primeira carga": nenhum dos filtros veio no GET
    initial_load = not any(k in request.GET for k in ["condominio", "dt_ini", "dt_fim", "destinatario"])

    # Defaults de primeira carga
    if initial_load:
        today = timezone.localdate().isoformat()  # 'YYYY-MM-DD'
        dt_ini = today
        dt_fim = today
        if not is_admin_like:
            first_allowed_id = allowed.order_by("nome").values_list("id", flat=True).first()
            condominio_id = str(first_allowed_id) if first_allowed_id else ""

    # --- aplica filtros ---
    if condominio_id:
        qs = qs.filter(condominio_id=condominio_id)

    if dt_ini:
        d0 = parse_date(dt_ini)
        if d0:
            qs = qs.filter(data_recebimento__date__gte=d0)

    if dt_fim:
        d1 = parse_date(dt_fim)
        if d1:
            qs = qs.filter(data_recebimento__date__lte=d1)

    if destinatario_q:
        # Se 'destinatario' for FK (ex.: Morador), filtra pelo campo de nome do relacionado
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
@permission_required('portaria.add_encomenda', raise_exception=True)
def encomenda_create(request):
    if request.method == 'POST':
        condominio_id = request.POST.get('condominio')
        unidade_id = request.POST.get('unidade')
        destinatario_id = request.POST.get('destinatario')
        Encomenda.objects.create(
        condominio_id=condominio_id,
        unidade_id=unidade_id,
        destinatario_id=destinatario_id,
        transportadora=request.POST.get('transportadora', ''),
        codigo_rastreamento=request.POST.get('codigo_rastreamento', ''),
        recebido_por=request.user,
        observacoes=request.POST.get('observacoes', ''),
        )
        return redirect('encomenda_list')

    return render(request, 'portaria/encomenda_form.html', {
    'condominios': Condominio.objects.all(),
    'unidades': Unidade.objects.all(),
    'moradores': Morador.objects.all(),
    })

@login_required
@permission_required('portaria.pode_entregar_encomenda', raise_exception=True)
def encomenda_entregar(request, pk):
    enc = get_object_or_404(Encomenda, pk=pk)
    if request.method == 'POST':
        enc.status = StatusEncomenda.ENTREGUE
        enc.data_entrega = timezone.now()
        enc.entregue_por = request.user
        enc.save()
        return redirect('encomenda_list')
    return render(request, 'portaria/encomenda_entregar_confirm.html', {'encomenda': enc})


#@login_required
#def acesso_list(request):
#    eventos = EventoAcesso.objects.select_related('condominio', 'unidade').order_by('-criado_em')[:200]
#    return render(request, 'portaria/acesso_list.html', {'eventos': eventos})

@login_required
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
        today_iso = timezone.localdate().isoformat()
        dt_ini = today_iso
        dt_fim = today_iso
        if not is_admin_like:
            first_allowed_id = allowed.order_by("nome").values_list("id", flat=True).first()
            condominio_id = str(first_allowed_id) if first_allowed_id else ""

    # Aplica filtros
    if condominio_id:
        qs = qs.filter(condominio_id=condominio_id)

    if dt_ini:
        d0 = parse_date(dt_ini)
        if d0:
            qs = qs.filter(criado_em__date__gte=d0)

    if dt_fim:
        d1 = parse_date(dt_fim)
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
@permission_required('portaria.pode_registrar_acesso', raise_exception=True)  # <- importante
def acesso_create(request):
    if request.method == 'POST':
        EventoAcesso.objects.create(
            condominio_id=request.POST.get('condominio'),
            unidade_id=request.POST.get('unidade') or None,
            pessoa_tipo=request.POST.get('pessoa_tipo'),
            pessoa_nome=request.POST.get('pessoa_nome'),
            documento=request.POST.get('documento', ''),
            metodo=request.POST.get('metodo'),
            resultado=request.POST.get('resultado'),
            motivo_negado=request.POST.get('motivo_negado', ''),
            criado_por=request.user,
        )
        return redirect('acesso_list')

    return render(request, 'portaria/acesso_form.html', {
        'condominios': Condominio.objects.all(),
        'unidades': Unidade.objects.all(),
        'tipos': TipoPessoa.choices,
        'metodos': MetodoAcesso.choices,
        'resultados': ResultadoAcesso.choices,
    })

@login_required
@permission_required('portaria.delete_encomenda', raise_exception=True)
@require_POST
def encomenda_delete(request, pk):
    # só permite excluir encomendas de condomínios que o usuário pode ver
    allowed = allowed_condominios_for(request.user)
    encomenda = get_object_or_404(Encomenda, pk=pk, condominio__in=allowed)

    encomenda.delete()
    messages.success(request, f'Encomenda #{pk} excluída com sucesso.')
    return redirect('encomenda_list')

@login_required
@permission_required('portaria.delete_eventoacesso', raise_exception=True)
@require_POST
def acesso_delete(request, pk):
    allowed = allowed_condominios_for(request.user)
    evento = get_object_or_404(EventoAcesso, pk=pk, condominio__in=allowed)
    evento.delete()
    messages.success(request, 'Registro de acesso excluído com sucesso.')
    return redirect('acesso_list')

#from .models import TipoPessoa, MetodoAcesso, ResultadoAcesso
#return render(request, 'portaria/acesso_form.html', {
#    'condominios': Condominio.objects.all(),
#    'unidades': Unidade.objects.all(),
#    'tipos': TipoPessoa.choices,
#    'metodos': MetodoAcesso.choices,
#    'resultados': ResultadoAcesso.choices,
#    })