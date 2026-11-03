from django.urls import path
from . import views
from .views import MeusPedidosView, PedidoDetailView

urlpatterns = [
    path('comprar/<slug:slug>/', views.comprar, name='comprar'),
    path('pedidos/', MeusPedidosView.as_view(), name='meus_pedidos'),
    path('pedidos/<int:pk>/', PedidoDetailView.as_view(), name='pedido_detalhes'),
    path('pedidos/<int:pk>/cupom/', views.aplicar_cupom, name='aplicar_cupom'),
    path('pedidos/<int:pk>/pagar/', views.pagar, name='pagar'),
]
