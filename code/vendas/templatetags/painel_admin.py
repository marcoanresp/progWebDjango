"""
Template tag usada na página inicial do ambiente administrativo
(templates/admin/index.html) para montar o painel de indicadores.
"""
import json
from datetime import timedelta
from decimal import Decimal

from django import template
from django.conf import settings
from django.db.models import Avg, F, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from cursos.filters import subquery_receita_curso
from cursos.models import Avaliacao, Curso, Matricula
from portal_cursos.admin_mixins import formatar_moeda
from vendas.models import ItemPedido, Pedido

register = template.Library()

MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


@register.simple_tag
def resumo_painel(usuario):
    vendedor = (not usuario.is_superuser) and hasattr(usuario, "perfil") and usuario.perfil.eh_vendedor

    cursos = Curso.objects.all()
    itens_pagos = ItemPedido.objects.filter(pedido__status=Pedido.Status.PAGO)
    matriculas = Matricula.objects.filter(ativa=True)
    avaliacoes = Avaliacao.objects.filter(aprovada=True)
    pedidos_pendentes = Pedido.objects.filter(status=Pedido.Status.PENDENTE)
    if vendedor:
        cursos = cursos.filter(vendedor=usuario)
        itens_pagos = itens_pagos.filter(curso__vendedor=usuario)
        matriculas = matriculas.filter(curso__vendedor=usuario)
        avaliacoes = avaliacoes.filter(curso__vendedor=usuario)
        pedidos_pendentes = pedidos_pendentes.filter(itens__curso__vendedor=usuario).distinct()

    receita = itens_pagos.aggregate(v=Sum(F("preco_unitario") - F("desconto")))["v"] or Decimal("0")
    if vendedor:  # o vendedor vê o valor líquido (após a taxa da plataforma)
        receita = receita * (1 - Decimal(str(settings.TAXA_PLATAFORMA)))
    media = avaliacoes.aggregate(m=Avg("nota"))["m"]

    # Receita dos últimos 6 meses (gráfico)
    inicio = (timezone.now().replace(day=1) - timedelta(days=150)).replace(day=1, hour=0, minute=0)
    por_mes = {
        r["mes"].strftime("%Y-%m"): float(r["total"] or 0)
        for r in itens_pagos.filter(pedido__pago_em__gte=inicio)
        .annotate(mes=TruncMonth("pedido__pago_em")).values("mes")
        .annotate(total=Sum(F("preco_unitario") - F("desconto"))).order_by("mes")
    }
    labels, valores = [], []
    ano, mes = inicio.year, inicio.month
    for _ in range(6):
        labels.append(f"{MESES[mes - 1]}/{str(ano)[2:]}")
        valores.append(por_mes.get(f"{ano}-{mes:02d}", 0))
        mes += 1
        if mes > 12:
            mes, ano = 1, ano + 1

    top_cursos = cursos.annotate(receita=subquery_receita_curso()).filter(receita__gt=0).order_by("-receita")[:5]

    return {
        "eh_vendedor": vendedor,
        "cards": [
            {"titulo": "Cursos publicados", "valor": cursos.filter(status=Curso.Status.PUBLICADO).count(),
             "icone": "fas fa-graduation-cap", "cor": "primary", "url": "cursos/curso/?status__exact=PUBLICADO"},
            {"titulo": "Aguardando revisão", "valor": cursos.filter(status=Curso.Status.EM_REVISAO).count(),
             "icone": "fas fa-hourglass-half", "cor": "warning", "url": "cursos/curso/?status__exact=EM_REVISAO"},
            {"titulo": "Matrículas ativas", "valor": matriculas.count(),
             "icone": "fas fa-user-graduate", "cor": "info", "url": "cursos/matricula/?ativa__exact=1"},
            {"titulo": "Receita líquida" if vendedor else "Receita total", "valor": formatar_moeda(receita),
             "icone": "fas fa-dollar-sign", "cor": "success", "url": "vendas/pedido/?status__exact=PAGO"},
            {"titulo": "Pedidos pendentes", "valor": pedidos_pendentes.count(),
             "icone": "fas fa-shopping-cart", "cor": "danger", "url": "vendas/pedido/?status__exact=PENDENTE"},
            {"titulo": "Nota média", "valor": f"{media:.1f} ★" if media else "-",
             "icone": "fas fa-star", "cor": "secondary", "url": "cursos/avaliacao/"},
        ],
        "grafico_labels": json.dumps(labels),
        "grafico_valores": json.dumps(valores),
        "top_cursos": [
            {"titulo": c.titulo, "receita": formatar_moeda(c.receita), "url": f"cursos/curso/{c.pk}/change/"}
            for c in top_cursos
        ],
    }
