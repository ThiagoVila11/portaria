from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from .models import Encomenda, EventoAcesso, StatusEncomenda, TipoPessoa, MetodoAcesso, ResultadoAcesso
from condominio.models import Condominio, Unidade, Morador


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
    encomendas = Encomenda.objects.select_related('destinatario', 'unidade', 'condominio').order_by('-data_recebimento')
    return render(request, 'portaria/encomenda_list.html', {'encomendas': encomendas})


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


@login_required
def acesso_list(request):
    eventos = EventoAcesso.objects.select_related('condominio', 'unidade').order_by('-criado_em')[:200]
    return render(request, 'portaria/acesso_list.html', {'eventos': eventos})


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


#from .models import TipoPessoa, MetodoAcesso, ResultadoAcesso
#return render(request, 'portaria/acesso_form.html', {
#    'condominios': Condominio.objects.all(),
#    'unidades': Unidade.objects.all(),
#    'tipos': TipoPessoa.choices,
#    'metodos': MetodoAcesso.choices,
#    'resultados': ResultadoAcesso.choices,
#    })