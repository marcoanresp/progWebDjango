from django.contrib import admin, messages
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.html import format_html

from cursos.models import Curso
from portal_cursos.admin_mixins import (VendedorRestritoMixin, badge, eh_vendedor, exportar_csv,
                                        formatar_moeda)

from .filters import (ComCupomFilter, OrigemCupomFilter, QuantidadeItensFilter, SituacaoCupomFilter,
                      ValorPedidoFilter, VendedorDoPedidoFilter)
from .models import Cupom, ItemPedido, Pedido

CORES_STATUS_PEDIDO = {
    Pedido.Status.PENDENTE: "warning",
    Pedido.Status.PAGO: "success",
    Pedido.Status.CANCELADO: "secondary",
    Pedido.Status.REEMBOLSADO: "danger",
}


# ---------------------------------------------------------------------------
# Cupom
# ---------------------------------------------------------------------------

@admin.register(Cupom)
class CupomAdmin(VendedorRestritoMixin, admin.ModelAdmin):
    filtros_somente_admin = (OrigemCupomFilter,)
    list_display = ("codigo", "tipo", "valor_formatado", "vendedor", "validade_inicio", "validade_fim",
                    "usos", "usos_maximos", "situacao", "ativo")
    list_editable = ("ativo",)
    list_filter = (SituacaoCupomFilter, "tipo", "ativo", OrigemCupomFilter,
                   ("validade_fim", admin.DateFieldListFilter))
    search_fields = ("codigo", "descricao", "vendedor__username")
    date_hierarchy = "validade_inicio"
    filter_horizontal = ("cursos",)
    autocomplete_fields = ("vendedor",)
    actions = ["ativar", "desativar"]
    fieldsets = (
        (None, {"fields": ("codigo", "descricao", "vendedor", "ativo")}),
        ("Desconto", {"fields": ("tipo", "valor", "cursos")}),
        ("Validade e limites", {"fields": ("validade_inicio", "validade_fim", "usos_maximos")}),
    )

    def get_queryset(self, request):
        # O contador do admin usa a mesma política de reserva que o checkout.
        return super().get_queryset(request).select_related("vendedor").annotate(
            n_usos=Count("pedidos", filter=Q(
                pedidos__status__in=[Pedido.Status.PENDENTE, Pedido.Status.PAGO])))

    def get_readonly_fields(self, request, obj=None):
        if eh_vendedor(request):
            return ("vendedor",)
        return ()

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "cursos" and eh_vendedor(request):
            kwargs["queryset"] = Curso.objects.filter(vendedor=request.user)
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if eh_vendedor(request):
            obj.vendedor = request.user  # cupom de vendedor vale apenas para os cursos dele
        super().save_model(request, obj, form, change)

    @admin.display(description="valor", ordering="valor")
    def valor_formatado(self, obj):
        if obj.tipo == Cupom.Tipo.PERCENTUAL:
            return f"{obj.valor:.0f}%"
        return formatar_moeda(obj.valor)

    @admin.display(description="usos", ordering="n_usos")
    def usos(self, obj):
        return obj.n_usos

    @admin.display(description="situação")
    def situacao(self, obj):
        agora = timezone.now()
        if not obj.ativo:
            return badge("Desativado", "secondary")
        if obj.validade_inicio > agora:
            return badge("Agendado", "info")
        if obj.validade_fim and obj.validade_fim < agora:
            return badge("Expirado", "dark")
        if obj.usos_maximos is not None and obj.n_usos >= obj.usos_maximos:
            return badge("Esgotado", "danger")
        return badge("Válido", "success")

    @admin.action(description="Ativar cupons")
    def ativar(self, request, queryset):
        self.message_user(request, f"{queryset.update(ativo=True)} cupom(ns) ativado(s).")

    @admin.action(description="Desativar cupons")
    def desativar(self, request, queryset):
        self.message_user(request, f"{queryset.update(ativo=False)} cupom(ns) desativado(s).")


# ---------------------------------------------------------------------------
# Pedido
# ---------------------------------------------------------------------------

class ItemPedidoInline(admin.TabularInline):
    model = ItemPedido
    fields = ("curso", "preco_unitario", "desconto", "valor_final_formatado")
    # O preço e o curso do item são snapshots; substituições exigem remover e adicionar outro item.
    readonly_fields = ("curso", "preco_unitario", "desconto", "valor_final_formatado")
    autocomplete_fields = ("curso",)
    extra = 0

    def has_add_permission(self, request, obj=None):
        return super().has_add_permission(request, obj) and (
            obj is None or obj.status == Pedido.Status.PENDENTE)

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and (
            obj is None or obj.status == Pedido.Status.PENDENTE)

    @admin.display(description="valor final")
    def valor_final_formatado(self, obj):
        return formatar_moeda(obj.valor_final) if obj.pk else "-"


@admin.register(Pedido)
class PedidoAdmin(VendedorRestritoMixin, admin.ModelAdmin):
    campo_vendedor = "itens__curso__vendedor"
    filtros_somente_admin = (VendedorDoPedidoFilter,)
    list_display = ("numero_pedido", "cliente", "status_colorido", "forma_pagamento", "qtd_itens",
                    "subtotal_fmt", "desconto_fmt", "total_fmt", "cupom", "criado_em", "pago_em")
    list_display_links = ("numero_pedido",)
    list_filter = ("status", "forma_pagamento", ValorPedidoFilter, ComCupomFilter, QuantidadeItensFilter,
                   VendedorDoPedidoFilter, ("itens__curso__categoria", admin.RelatedOnlyFieldListFilter),
                   ("criado_em", admin.DateFieldListFilter), ("pago_em", admin.DateFieldListFilter))
    search_fields = ("=id", "cliente__username", "cliente__email", "cliente__first_name",
                     "cupom__codigo", "itens__curso__titulo")
    date_hierarchy = "criado_em"
    list_select_related = ("cliente", "cupom")
    autocomplete_fields = ("cliente", "cupom")
    # Alterações de status e aplicação de cupom devem passar pelos fluxos controlados do modelo/site.
    readonly_fields = ("status", "cupom", "subtotal", "desconto", "total", "criado_em", "pago_em")
    inlines = [ItemPedidoInline]
    actions = ["confirmar_pagamento", "cancelar", "reembolsar", exportar_csv]
    fieldsets = (
        ("Cliente e pagamento", {"fields": ("cliente", "status", "forma_pagamento", "parcelas", "cupom")}),
        ("Valores (calculados automaticamente)", {"fields": ("subtotal", "desconto", "total")}),
        ("Datas", {"fields": ("criado_em", "pago_em")}),
        ("Observações", {"fields": ("observacoes",), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(n_itens=Count("itens", distinct=True))

    def get_readonly_fields(self, request, obj=None):
        # Evita trocar o cliente ou os dados de pagamento depois que o pedido foi criado/pago.
        campos = list(super().get_readonly_fields(request, obj))
        if obj:
            campos.append("cliente")
            if obj.status != Pedido.Status.PENDENTE:
                campos.extend(("forma_pagamento", "parcelas"))
        return campos

    def get_actions(self, request):
        acoes = super().get_actions(request)
        if eh_vendedor(request):  # vendedor apenas consulta as vendas
            for nome in ("confirmar_pagamento", "cancelar", "reembolsar"):
                acoes.pop(nome, None)
        return acoes

    def save_related(self, request, form, formsets, change):
        """Depois de salvar os itens, recalcula os totais apenas de pedidos pendentes."""
        super().save_related(request, form, formsets, change)
        pedido = form.instance
        # O admin só recalcula pedidos pendentes; pedidos encerrados preservam o histórico financeiro.
        if pedido.status == Pedido.Status.PENDENTE:
            pedido.recalcular_totais()

    # ----- Colunas -----
    @admin.display(description="pedido", ordering="id")
    def numero_pedido(self, obj):
        return f"#{obj.numero}"

    @admin.display(description="status", ordering="status")
    def status_colorido(self, obj):
        return badge(obj.get_status_display(), CORES_STATUS_PEDIDO.get(obj.status, "secondary"))

    @admin.display(description="cursos", ordering="n_itens")
    def qtd_itens(self, obj):
        return obj.n_itens

    @admin.display(description="subtotal", ordering="subtotal")
    def subtotal_fmt(self, obj):
        return formatar_moeda(obj.subtotal)

    @admin.display(description="desconto", ordering="desconto")
    def desconto_fmt(self, obj):
        if obj.desconto:
            return format_html('<span class="text-danger">- {}</span>', formatar_moeda(obj.desconto))
        return "-"

    @admin.display(description="total", ordering="total")
    def total_fmt(self, obj):
        return format_html("<b>{}</b>", formatar_moeda(obj.total))

    # ----- Ações -----
    @admin.action(description="Confirmar pagamento (libera os cursos)")
    def confirmar_pagamento(self, request, queryset):
        pedidos = queryset.filter(status=Pedido.Status.PENDENTE)
        n = 0
        for pedido in pedidos:
            pedido.confirmar_pagamento()
            n += 1
        self.message_user(request, f"{n} pedido(s) confirmado(s) e matrícula(s) liberada(s).", messages.SUCCESS)

    @admin.action(description="Cancelar pedidos")
    def cancelar(self, request, queryset):
        # Cancelamento encerra apenas pedidos pendentes; pagos exigem ação de reembolso.
        for pedido in queryset.filter(status=Pedido.Status.PENDENTE):
            pedido.cancelar()
        self.message_user(request, "Pedido(s) pendente(s) cancelado(s).", messages.WARNING)

    @admin.action(description="Reembolsar pedidos pagos")
    def reembolsar(self, request, queryset):
        for pedido in queryset.filter(status=Pedido.Status.PAGO):
            pedido.cancelar(reembolso=True)
        self.message_user(request, "Pedido(s) reembolsado(s) e acesso removido.", messages.WARNING)
