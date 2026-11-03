"""
Recursos compartilhados pelos ModelAdmin dos apps.
"""
import csv

from django.contrib import admin
from django.http import HttpResponse
from django.utils.html import format_html


def formatar_moeda(valor):
    """Formata um número no padrão brasileiro: R$ 1.234,56."""
    if valor is None:
        return "-"
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def badge(texto, cor):
    """Etiqueta colorida do Bootstrap para exibir status na listagem."""
    return format_html('<span class="badge bg-{}">{}</span>', cor, texto)


def eh_vendedor(request):
    """True quando o usuário logado é um vendedor (não administrador da plataforma)."""
    usuario = request.user
    return (not usuario.is_superuser) and hasattr(usuario, "perfil") and usuario.perfil.eh_vendedor


class VendedorRestritoMixin:
    """
    Restringe os dados exibidos no admin para vendedores: cada vendedor só
    enxerga (e altera) os registros ligados aos seus próprios cursos.

    Cada ModelAdmin informa em `campo_vendedor` o caminho até o vendedor,
    ex.: "vendedor", "curso__vendedor", "modulo__curso__vendedor".
    Filtros que só fazem sentido para o administrador ficam em `filtros_somente_admin`.
    """

    campo_vendedor = "vendedor"
    filtros_somente_admin = ()

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if eh_vendedor(request):
            qs = qs.filter(**{self.campo_vendedor: request.user}).distinct()
        return qs

    def get_list_filter(self, request):
        filtros = super().get_list_filter(request)
        if eh_vendedor(request):
            filtros = [f for f in filtros if f not in self.filtros_somente_admin]
        return filtros


@admin.action(description="Exportar selecionados para CSV")
def exportar_csv(modeladmin, request, queryset):
    """Ação genérica: exporta os campos simples do model para um arquivo CSV."""
    meta = modeladmin.model._meta
    campos = [f for f in meta.fields]
    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = f'attachment; filename="{meta.model_name}.csv"'
    resposta.write("﻿")  # BOM para o Excel reconhecer acentos
    escritor = csv.writer(resposta, delimiter=";")
    escritor.writerow([str(f.verbose_name) for f in campos])
    for obj in queryset:
        linha = []
        for f in campos:
            valor = getattr(obj, f.name)
            if f.choices:
                valor = getattr(obj, f"get_{f.name}_display")()
            linha.append(valor)
        escritor.writerow(linha)
    return resposta
