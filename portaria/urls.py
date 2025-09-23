from django.urls import path
from . import views_salesforce as sfv
from . import views


urlpatterns = [
path('', views.dashboard, name='dashboard'),


path('encomendas/', views.encomenda_list, name='encomenda_list'),
path('encomendas/nova/', views.encomenda_create, name='encomenda_create'),
path('encomendas/<uuid:pk>/entregar/', views.encomenda_entregar, name='encomenda_entregar'),
path('encomendas/<uuid:pk>/excluir/', views.encomenda_delete, name='encomenda_delete'),
path('encomendas/<uuid:pk>/editar/', views.encomenda_edit, name='encomenda_edit'),


path('acessos/', views.acesso_list, name='acesso_list'),
path('acessos/novo/', views.acesso_create, name='acesso_create'),
path('acessos/<uuid:pk>/excluir/', views.acesso_delete, name='acesso_delete'),
path('acessos/<uuid:pk>/editar/', views.acesso_edit, name='acesso_edit'),

path("sf/tickets/",  sfv.sf_tickets_list,  name="sf_tickets_list"),
path("sf/visitors/", sfv.sf_visitors_list, name="sf_visitors_list"),

path("ajax/unidades/<int:condominio_id>/", views.ajax_unidades_por_condominio, name="ajax_unidades_por_condominio"),
path("ajax/moradores/<int:unidade_id>/", views.ajax_moradores_por_unidade, name="ajax_moradores_por_unidade"),
path("visitantes/preaprovados/", views.visitantes_preaprovados, name="visitantes_preaprovados"),

]