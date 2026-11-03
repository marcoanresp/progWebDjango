from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.utils.html import format_html

from portal_cursos.admin_mixins import VendedorRestritoMixin, badge, eh_vendedor, exportar_csv

from .filters import AtividadeVendedorFilter, ComprasClienteFilter, PerfilCompletoFilter, TipoUsuarioFilter
from .models import Perfil

CORES_TIPO = {Perfil.Tipo.CLIENTE: "info", Perfil.Tipo.VENDEDOR: "primary"}


class PerfilInline(admin.StackedInline):
    model = Perfil
    can_delete = False
    fk_name = "usuario"
    fieldsets = (
        (None, {"fields": ("tipo", "foto", "bio", "telefone", "data_nascimento")}),
        ("Dados de vendedor", {"fields": ("titulo_profissional", "site", "chave_pix", "verificado")}),
    )


# Substitui o admin padrão de User para incluir o perfil e novos filtros
admin.site.unregister(User)


@admin.register(User)
class UsuarioAdmin(BaseUserAdmin):
    inlines = [PerfilInline]
    list_display = ("username", "email", "first_name", "last_name", "tipo", "qtd_compras",
                    "is_staff", "is_active", "date_joined")
    list_filter = (TipoUsuarioFilter, ComprasClienteFilter, "is_active", "is_staff", "is_superuser",
                   "groups", ("date_joined", admin.DateFieldListFilter))
    search_fields = ("username", "email", "first_name", "last_name")
    date_hierarchy = "date_joined"
    list_select_related = ("perfil",)
    actions = ["ativar", "desativar", exportar_csv]

    def get_inline_instances(self, request, obj=None):
        # Na tela de criação o perfil é gerado pelo sinal post_save; o inline aparece só na edição.
        if obj is None:
            return []
        return super().get_inline_instances(request, obj)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            n_compras=Count("pedidos", filter=Q(pedidos__status="PAGO"), distinct=True))

    @admin.display(description="tipo", ordering="perfil__tipo")
    def tipo(self, obj):
        if obj.is_superuser:
            return badge("Administrador", "danger")
        perfil = getattr(obj, "perfil", None)
        if perfil is None:
            return "-"
        return badge(perfil.get_tipo_display(), CORES_TIPO.get(perfil.tipo, "secondary"))

    @admin.display(description="compras", ordering="n_compras")
    def qtd_compras(self, obj):
        return obj.n_compras

    @admin.action(description="Ativar usuários")
    def ativar(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_active=True)} usuário(s) ativado(s).")

    @admin.action(description="Desativar usuários (bloqueia o login)")
    def desativar(self, request, queryset):
        n = queryset.exclude(pk=request.user.pk).update(is_active=False)
        self.message_user(request, f"{n} usuário(s) desativado(s).", messages.WARNING)


@admin.register(Perfil)
class PerfilAdmin(VendedorRestritoMixin, admin.ModelAdmin):
    campo_vendedor = "usuario"  # o vendedor só vê e edita o próprio perfil
    list_display = ("foto_miniatura", "usuario", "nome", "tipo_colorido", "titulo_profissional",
                    "qtd_cursos", "verificado", "criado_em")
    list_display_links = ("foto_miniatura", "usuario")
    list_filter = ("tipo", "verificado", AtividadeVendedorFilter, PerfilCompletoFilter,
                   ("criado_em", admin.DateFieldListFilter))
    filtros_somente_admin = ("tipo", "verificado", AtividadeVendedorFilter, PerfilCompletoFilter)
    search_fields = ("usuario__username", "usuario__first_name", "usuario__last_name",
                     "usuario__email", "titulo_profissional")
    list_select_related = ("usuario",)
    readonly_fields = ("criado_em", "atualizado_em")
    actions = ["verificar", "tornar_vendedor", "tornar_cliente"]
    fieldsets = (
        (None, {"fields": ("usuario", "tipo", "foto", "bio", "telefone", "data_nascimento")}),
        ("Dados de vendedor", {"fields": ("titulo_profissional", "site", "chave_pix", "verificado")}),
        ("Datas", {"fields": ("criado_em", "atualizado_em"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(n_cursos=Count("usuario__cursos_vendidos"))

    def get_readonly_fields(self, request, obj=None):
        campos = list(super().get_readonly_fields(request, obj))
        if eh_vendedor(request):
            campos += ["usuario", "tipo", "verificado"]
        return campos

    def get_actions(self, request):
        if eh_vendedor(request):
            return {}
        return super().get_actions(request)

    def has_add_permission(self, request):
        return False  # perfis são criados automaticamente junto com o usuário

    @admin.display(description="foto")
    def foto_miniatura(self, obj):
        if obj.foto:
            return format_html('<img src="{}" class="avatar-admin" alt="">', obj.foto.url)
        return format_html('<i class="fas fa-user-circle fa-2x text-muted"></i>')

    @admin.display(description="nome", ordering="usuario__first_name")
    def nome(self, obj):
        return obj.usuario.get_full_name() or "-"

    @admin.display(description="tipo", ordering="tipo")
    def tipo_colorido(self, obj):
        return badge(obj.get_tipo_display(), CORES_TIPO.get(obj.tipo, "secondary"))

    @admin.display(description="cursos", ordering="n_cursos")
    def qtd_cursos(self, obj):
        return obj.n_cursos if obj.eh_vendedor else "-"

    @admin.action(description="Marcar vendedores como verificados")
    def verificar(self, request, queryset):
        n = queryset.filter(tipo=Perfil.Tipo.VENDEDOR).update(verificado=True)
        self.message_user(request, f"{n} vendedor(es) verificado(s).", messages.SUCCESS)

    @admin.action(description="Transformar em vendedor")
    def tornar_vendedor(self, request, queryset):
        for perfil in queryset:
            perfil.tipo = Perfil.Tipo.VENDEDOR
            perfil.save()  # o sinal ajusta grupo e acesso ao admin
        self.message_user(request, "Perfil(is) alterado(s) para vendedor.")

    @admin.action(description="Transformar em cliente")
    def tornar_cliente(self, request, queryset):
        for perfil in queryset:
            perfil.tipo = Perfil.Tipo.CLIENTE
            perfil.save()
        self.message_user(request, "Perfil(is) alterado(s) para cliente.")
