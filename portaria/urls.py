from django.urls import path
from . import views


urlpatterns = [
path('', views.dashboard, name='dashboard'),


path('encomendas/', views.encomenda_list, name='encomenda_list'),
path('encomendas/nova/', views.encomenda_create, name='encomenda_create'),
path('encomendas/<uuid:pk>/entregar/', views.encomenda_entregar, name='encomenda_entregar'),


path('acessos/', views.acesso_list, name='acesso_list'),
path('acessos/novo/', views.acesso_create, name='acesso_create'),
]