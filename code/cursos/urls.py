from django.urls import path
from . import api
from . import views
from .views import (AssistirCursoView, CursoDetailView, CursoListView, MeusCursosView, PainelVendedorView,
                    PrincipalView)

urlpatterns = [
    path('', PrincipalView.as_view(), name='principal'),
    path('cursos/', CursoListView.as_view(), name='cursos'),
    path('cursos/<slug:slug>/', CursoDetailView.as_view(), name='curso_detalhes'),
    path('cursos/<slug:slug>/avaliar/', views.avaliar_curso, name='avaliar_curso'),
    path('cursos/<slug:slug>/avaliar/excluir/', views.excluir_avaliacao, name='excluir_avaliacao'),
    path('meus-cursos/', MeusCursosView.as_view(), name='meus_cursos'),
    path('meus-cursos/<slug:slug>/', AssistirCursoView.as_view(), name='assistir_curso'),
    path('vendedor/', PainelVendedorView.as_view(), name='painel_vendedor'),

    # API JSON (frontend Vue)
    path('api/cursos/', api.api_cursos, name='api_cursos'),
    path('api/cursos/<slug:slug>/', api.api_curso_detalhes, name='api_curso_detalhes'),
    path('api/categorias/', api.api_categorias, name='api_categorias'),
]
