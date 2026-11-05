from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView

from cursos.models import Curso, Matricula

from .models import Cupom, ItemPedido, Pedido


@login_required
@require_POST
@transaction.atomic
def comprar(request, slug):
    """Cria um pedido (aguardando pagamento) com o curso escolhido."""
    # Serializa compras do mesmo usuário e impede pedidos pendentes duplicados no fluxo normal.
    User.objects.select_for_update().get(pk=request.user.pk)
    curso = get_object_or_404(
        Curso.objects.select_for_update(), slug=slug, status=Curso.Status.PUBLICADO)
    if curso.vendedor_id == request.user.id:
        messages.warning(request, 'Você não pode comprar o seu próprio curso.')
        return redirect('curso_detalhes', slug=slug)
    if Matricula.objects.filter(aluno=request.user, curso=curso, ativa=True).exists():
        messages.info(request, 'Você já possui este curso.')
        return redirect('assistir_curso', slug=slug)
    pedido_existente = Pedido.objects.filter(
        cliente=request.user, status=Pedido.Status.PENDENTE, itens__curso=curso).first()
    if pedido_existente:
        messages.info(request, 'Já existe um pedido pendente para este curso.')
        return redirect('pedido_detalhes', pk=pedido_existente.pk)

    pedido = Pedido.objects.create(cliente=request.user)
    ItemPedido.objects.create(pedido=pedido, curso=curso)
    pedido.recalcular_totais()

    if pedido.total == 0:  # curso gratuito: libera na hora
        pedido.confirmar_pagamento()
        messages.success(request, 'Inscrição realizada! Bons estudos.')
        return redirect('assistir_curso', slug=slug)
    return redirect('pedido_detalhes', pk=pedido.pk)


@login_required
@require_POST
def aplicar_cupom(request, pk):
    pedido = get_object_or_404(Pedido, pk=pk, cliente=request.user, status=Pedido.Status.PENDENTE)
    codigo = request.POST.get('cupom', '').strip().upper()
    cupom = Cupom.objects.filter(codigo=codigo).first()
    if not cupom:
        messages.error(request, 'Cupom inválido ou expirado.')
    else:
        # A validação, reserva de uso e gravação do desconto são feitas juntas no modelo.
        try:
            pedido.aplicar_cupom(cupom)
        except ValidationError as erro:
            messages.error(request, ' '.join(erro.messages))
        else:
            messages.success(request, f'Cupom {cupom.codigo} aplicado!')
    return redirect('pedido_detalhes', pk=pk)


@login_required
@require_POST
def pagar(request, pk):
    """Pagamento simulado: em um sistema real aqui entraria a integração com o gateway."""
    pedido = get_object_or_404(Pedido, pk=pk, cliente=request.user, status=Pedido.Status.PENDENTE)
    forma = request.POST.get('forma_pagamento', Pedido.FormaPagamento.PIX)
    if forma in Pedido.FormaPagamento.values:
        pedido.forma_pagamento = forma
        pedido.save(update_fields=['forma_pagamento'])
    pedido.confirmar_pagamento()
    messages.success(request, 'Pagamento confirmado! Seus cursos já estão disponíveis.')
    return redirect('meus_cursos')


class MeusPedidosView(LoginRequiredMixin, ListView):
    template_name = "meus_pedidos.html"
    context_object_name = "pedidos"

    def get_queryset(self):
        return Pedido.objects.filter(cliente=self.request.user).prefetch_related("itens__curso")


class PedidoDetailView(LoginRequiredMixin, DetailView):
    template_name = "pedido_detalhes.html"
    context_object_name = "pedido"

    def get_queryset(self):
        return Pedido.objects.filter(cliente=self.request.user).prefetch_related("itens__curso")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["formas_pagamento"] = Pedido.FormaPagamento.choices
        return context
