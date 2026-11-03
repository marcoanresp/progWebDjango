from django.contrib import admin
from django.db.models import Count, Q


class TipoUsuarioFilter(admin.SimpleListFilter):
    title = "tipo de usuário"
    parameter_name = "tipo"

    def lookups(self, request, model_admin):
        return [("CLIENTE", "Clientes"), ("VENDEDOR", "Vendedores"), ("ADMIN", "Administradores")]

    def queryset(self, request, queryset):
        if self.value() == "ADMIN":
            return queryset.filter(is_superuser=True)
        if self.value() in ("CLIENTE", "VENDEDOR"):
            return queryset.filter(perfil__tipo=self.value(), is_superuser=False)
        return queryset


class AtividadeVendedorFilter(admin.SimpleListFilter):
    title = "atividade como vendedor"
    parameter_name = "atividade"

    def lookups(self, request, model_admin):
        return [("publicados", "Com cursos publicados"), ("sem_cursos", "Vendedor sem cursos")]

    def queryset(self, request, queryset):
        if self.value() == "publicados":
            return queryset.filter(usuario__cursos_vendidos__status="PUBLICADO").distinct()
        if self.value() == "sem_cursos":
            return queryset.filter(tipo="VENDEDOR").annotate(
                _n=Count("usuario__cursos_vendidos")).filter(_n=0)
        return queryset


class PerfilCompletoFilter(admin.SimpleListFilter):
    title = "perfil completo"
    parameter_name = "completo"

    def lookups(self, request, model_admin):
        return [("sim", "Completo (foto e bio)"), ("nao", "Incompleto")]

    def queryset(self, request, queryset):
        completo = Q(bio__gt="") & ~Q(foto="") & Q(foto__isnull=False)
        if self.value() == "sim":
            return queryset.filter(completo)
        if self.value() == "nao":
            return queryset.exclude(completo)
        return queryset


class ComprasClienteFilter(admin.SimpleListFilter):
    title = "compras"
    parameter_name = "compras"

    def lookups(self, request, model_admin):
        return [("nenhuma", "Nunca comprou"), ("1", "1 compra"), ("2+", "2 ou mais compras")]

    def queryset(self, request, queryset):
        qs = queryset.annotate(_compras=Count("pedidos", filter=Q(pedidos__status="PAGO"), distinct=True))
        if self.value() == "nenhuma":
            return qs.filter(_compras=0)
        if self.value() == "1":
            return qs.filter(_compras=1)
        if self.value() == "2+":
            return qs.filter(_compras__gte=2)
        return queryset
