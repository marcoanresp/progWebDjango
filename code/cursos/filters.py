"""
Filtros personalizados do ambiente administrativo (barra lateral "Filtrar").
Cada classe herda de SimpleListFilter e define:
  - lookups(): as opções exibidas;
  - queryset(): como o queryset é filtrado para a opção escolhida.
"""
from django.contrib import admin
from django.contrib.auth.models import User
from django.db.models import Avg, Count, DecimalField, F, OuterRef, Q, Subquery, Sum


def subquery_receita_curso():
    """
    Subquery com a receita (itens de pedidos pagos, já com desconto) de cada curso.
    Usamos Subquery em vez de Sum("itens_vendidos__...") para não multiplicar
    os valores quando a consulta também faz JOIN com matrículas ou avaliações.
    """
    from vendas.models import ItemPedido
    return Subquery(
        ItemPedido.objects.filter(curso=OuterRef("pk"), pedido__status="PAGO")
        .values("curso")
        .annotate(total=Sum(F("preco_unitario") - F("desconto")))
        .values("total"),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )


class FaixaPrecoFilter(admin.SimpleListFilter):
    title = "faixa de preço"
    parameter_name = "faixa_preco"

    def lookups(self, request, model_admin):
        return [
            ("gratuito", "Gratuito"),
            ("ate50", "Até R$ 50"),
            ("50a150", "R$ 50 a R$ 150"),
            ("150a300", "R$ 150 a R$ 300"),
            ("acima300", "Acima de R$ 300"),
        ]

    def queryset(self, request, queryset):
        faixas = {
            "gratuito": Q(preco=0),
            "ate50": Q(preco__gt=0, preco__lte=50),
            "50a150": Q(preco__gt=50, preco__lte=150),
            "150a300": Q(preco__gt=150, preco__lte=300),
            "acima300": Q(preco__gt=300),
        }
        if self.value() in faixas:
            return queryset.filter(faixas[self.value()])
        return queryset


class EmPromocaoFilter(admin.SimpleListFilter):
    title = "em promoção"
    parameter_name = "promocao"

    def lookups(self, request, model_admin):
        return [("sim", "Sim"), ("nao", "Não")]

    def queryset(self, request, queryset):
        if self.value() == "sim":
            return queryset.filter(preco_promocional__isnull=False)
        if self.value() == "nao":
            return queryset.filter(preco_promocional__isnull=True)
        return queryset


class NotaMediaFilter(admin.SimpleListFilter):
    title = "nota média"
    parameter_name = "nota"

    def lookups(self, request, model_admin):
        return [
            ("4", "★★★★ 4 ou mais"),
            ("3", "★★★ entre 3 e 4"),
            ("baixa", "Abaixo de 3"),
            ("sem", "Sem avaliações"),
        ]

    def queryset(self, request, queryset):
        qs = queryset.annotate(_media=Avg("avaliacoes__nota", filter=Q(avaliacoes__aprovada=True)))
        if self.value() == "4":
            return qs.filter(_media__gte=4)
        if self.value() == "3":
            return qs.filter(_media__gte=3, _media__lt=4)
        if self.value() == "baixa":
            return qs.filter(_media__lt=3)
        if self.value() == "sem":
            return qs.filter(_media__isnull=True)
        return queryset


class PopularidadeFilter(admin.SimpleListFilter):
    title = "número de alunos"
    parameter_name = "alunos"

    def lookups(self, request, model_admin):
        return [
            ("0", "Nenhum aluno"),
            ("1a10", "1 a 10 alunos"),
            ("11a50", "11 a 50 alunos"),
            ("50+", "Mais de 50 alunos"),
        ]

    def queryset(self, request, queryset):
        qs = queryset.annotate(_alunos=Count("matriculas", filter=Q(matriculas__ativa=True), distinct=True))
        if self.value() == "0":
            return qs.filter(_alunos=0)
        if self.value() == "1a10":
            return qs.filter(_alunos__gte=1, _alunos__lte=10)
        if self.value() == "11a50":
            return qs.filter(_alunos__gte=11, _alunos__lte=50)
        if self.value() == "50+":
            return qs.filter(_alunos__gt=50)
        return queryset


class ConteudoCursoFilter(admin.SimpleListFilter):
    title = "conteúdo"
    parameter_name = "conteudo"

    def lookups(self, request, model_admin):
        return [
            ("sem_modulos", "Sem módulos"),
            ("sem_aulas", "Sem aulas"),
            ("com_previa", "Com aula de prévia gratuita"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "sem_modulos":
            return queryset.filter(modulos__isnull=True)
        if self.value() == "sem_aulas":
            return queryset.annotate(_aulas=Count("modulos__aulas")).filter(_aulas=0)
        if self.value() == "com_previa":
            return queryset.filter(modulos__aulas__previa_gratuita=True).distinct()
        return queryset


class VendedorFilter(admin.SimpleListFilter):
    """Lista apenas usuários com perfil de vendedor (mais útil que listar todos os usuários)."""
    title = "vendedor"
    parameter_name = "vendedor"
    campo = "vendedor"  # caminho até o usuário vendedor no model filtrado

    def lookups(self, request, model_admin):
        vendedores = User.objects.filter(perfil__tipo="VENDEDOR").order_by("first_name", "username")
        return [(v.pk, v.get_full_name() or v.username) for v in vendedores]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(**{self.campo: self.value()}).distinct()
        return queryset


class VendedorDoCursoFilter(VendedorFilter):
    campo = "curso__vendedor"


class VendedorDaAulaFilter(VendedorFilter):
    campo = "modulo__curso__vendedor"


class DuracaoAulaFilter(admin.SimpleListFilter):
    title = "duração"
    parameter_name = "duracao"

    def lookups(self, request, model_admin):
        return [
            ("curta", "Curta (até 10 min)"),
            ("media", "Média (10 a 30 min)"),
            ("longa", "Longa (mais de 30 min)"),
            ("zero", "Sem duração informada"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "curta":
            return queryset.filter(duracao_minutos__gt=0, duracao_minutos__lte=10)
        if self.value() == "media":
            return queryset.filter(duracao_minutos__gt=10, duracao_minutos__lte=30)
        if self.value() == "longa":
            return queryset.filter(duracao_minutos__gt=30)
        if self.value() == "zero":
            return queryset.filter(duracao_minutos=0)
        return queryset


class TipoCategoriaFilter(admin.SimpleListFilter):
    title = "hierarquia"
    parameter_name = "hierarquia"

    def lookups(self, request, model_admin):
        return [("principal", "Categorias principais"), ("sub", "Subcategorias")]

    def queryset(self, request, queryset):
        if self.value() == "principal":
            return queryset.filter(categoria_pai__isnull=True)
        if self.value() == "sub":
            return queryset.filter(categoria_pai__isnull=False)
        return queryset


class ProgressoMatriculaFilter(admin.SimpleListFilter):
    title = "progresso"
    parameter_name = "progresso"

    def lookups(self, request, model_admin):
        return [
            ("nao_iniciado", "Não iniciado"),
            ("andamento", "Em andamento"),
            ("concluido", "Concluído"),
        ]

    def queryset(self, request, queryset):
        qs = queryset.annotate(_feitas=Count("progressos", filter=Q(progressos__concluida=True)))
        if self.value() == "nao_iniciado":
            return qs.filter(_feitas=0, concluida_em__isnull=True)
        if self.value() == "andamento":
            return qs.filter(_feitas__gt=0, concluida_em__isnull=True)
        if self.value() == "concluido":
            return queryset.filter(concluida_em__isnull=False)
        return queryset


class EstrelasFilter(admin.SimpleListFilter):
    title = "nota"
    parameter_name = "estrelas"

    def lookups(self, request, model_admin):
        return [(str(n), "★" * n) for n in range(5, 0, -1)]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(nota=self.value())
        return queryset


class ComComentarioFilter(admin.SimpleListFilter):
    title = "comentário"
    parameter_name = "comentario"

    def lookups(self, request, model_admin):
        return [("sim", "Com comentário"), ("nao", "Somente nota")]

    def queryset(self, request, queryset):
        if self.value() == "sim":
            return queryset.exclude(comentario="")
        if self.value() == "nao":
            return queryset.filter(comentario="")
        return queryset


class ReceitaCursoFilter(admin.SimpleListFilter):
    title = "receita gerada"
    parameter_name = "receita"

    def lookups(self, request, model_admin):
        return [("0", "Sem vendas"), ("ate1000", "Até R$ 1.000"), ("1000+", "Acima de R$ 1.000")]

    def queryset(self, request, queryset):
        qs = queryset.annotate(_receita=subquery_receita_curso())
        if self.value() == "0":
            return qs.filter(_receita__isnull=True)
        if self.value() == "ate1000":
            return qs.filter(_receita__gt=0, _receita__lte=1000)
        if self.value() == "1000+":
            return qs.filter(_receita__gt=1000)
        return queryset
