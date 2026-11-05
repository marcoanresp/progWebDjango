from django.contrib import admin
from django.db.models import Count, F, Q
from django.utils import timezone

from cursos.filters import VendedorFilter


class ValorPedidoFilter(admin.SimpleListFilter):
    title = "valor do pedido"
    parameter_name = "valor"

    def lookups(self, request, model_admin):
        return [
            ("ate100", "Até R$ 100"),
            ("100a500", "R$ 100 a R$ 500"),
            ("acima500", "Acima de R$ 500"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "ate100":
            return queryset.filter(total__lte=100)
        if self.value() == "100a500":
            return queryset.filter(total__gt=100, total__lte=500)
        if self.value() == "acima500":
            return queryset.filter(total__gt=500)
        return queryset


class ComCupomFilter(admin.SimpleListFilter):
    title = "uso de cupom"
    parameter_name = "com_cupom"

    def lookups(self, request, model_admin):
        return [("sim", "Com cupom"), ("nao", "Sem cupom")]

    def queryset(self, request, queryset):
        if self.value() == "sim":
            return queryset.filter(cupom__isnull=False)
        if self.value() == "nao":
            return queryset.filter(cupom__isnull=True)
        return queryset


class QuantidadeItensFilter(admin.SimpleListFilter):
    title = "quantidade de cursos"
    parameter_name = "qtd_itens"

    def lookups(self, request, model_admin):
        return [("1", "1 curso"), ("2+", "2 ou mais cursos")]

    def queryset(self, request, queryset):
        qs = queryset.annotate(_itens=Count("itens", distinct=True))
        if self.value() == "1":
            return qs.filter(_itens=1)
        if self.value() == "2+":
            return qs.filter(_itens__gte=2)
        return queryset


class VendedorDoPedidoFilter(VendedorFilter):
    campo = "itens__curso__vendedor"


class SituacaoCupomFilter(admin.SimpleListFilter):
    title = "situação"
    parameter_name = "situacao"

    def lookups(self, request, model_admin):
        return [
            ("valido", "Válido agora"),
            ("agendado", "Agendado (ainda não começou)"),
            ("expirado", "Expirado"),
            ("esgotado", "Esgotado"),
            ("inativo", "Desativado"),
        ]

    def queryset(self, request, queryset):
        agora = timezone.now()
        # Pedidos reembolsados não consomem uso, como definido pela regra do cupom.
        qs = queryset.annotate(_usos=Count(
            "pedidos", filter=Q(pedidos__status__in=["PENDENTE", "PAGO"])))
        esgotado = Q(usos_maximos__isnull=False, _usos__gte=F("usos_maximos"))
        expirado = Q(validade_fim__isnull=False, validade_fim__lt=agora)
        if self.value() == "valido":
            return qs.filter(ativo=True, validade_inicio__lte=agora).exclude(expirado).exclude(esgotado)
        if self.value() == "agendado":
            return qs.filter(ativo=True, validade_inicio__gt=agora)
        if self.value() == "expirado":
            return qs.filter(expirado)
        if self.value() == "esgotado":
            return qs.filter(esgotado)
        if self.value() == "inativo":
            return qs.filter(ativo=False)
        return queryset


class OrigemCupomFilter(admin.SimpleListFilter):
    title = "origem do cupom"
    parameter_name = "origem"

    def lookups(self, request, model_admin):
        return [("plataforma", "Da plataforma"), ("vendedor", "De vendedor")]

    def queryset(self, request, queryset):
        if self.value() == "plataforma":
            return queryset.filter(vendedor__isnull=True)
        if self.value() == "vendedor":
            return queryset.filter(vendedor__isnull=False)
        return queryset
