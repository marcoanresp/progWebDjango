from django.contrib import admin, messages
from django.db.models import Avg, Count, Q, Sum
from django.utils.html import format_html

from portal_cursos.admin_mixins import (VendedorRestritoMixin, badge, eh_vendedor, exportar_csv,
                                        formatar_moeda)

from .filters import (ComComentarioFilter, ConteudoCursoFilter, DuracaoAulaFilter, EmPromocaoFilter,
                      EstrelasFilter, FaixaPrecoFilter, NotaMediaFilter, PopularidadeFilter,
                      ProgressoMatriculaFilter, ReceitaCursoFilter, TipoCategoriaFilter,
                      VendedorDaAulaFilter, VendedorDoCursoFilter, VendedorFilter,
                      subquery_receita_curso)
from .models import Aula, Avaliacao, Categoria, Curso, Matricula, Modulo, ProgressoAula, Tag

CORES_STATUS_CURSO = {
    Curso.Status.RASCUNHO: "secondary",
    Curso.Status.EM_REVISAO: "warning",
    Curso.Status.PUBLICADO: "success",
    Curso.Status.ARQUIVADO: "dark",
}


# ---------------------------------------------------------------------------
# Categoria e Tag (gerenciadas pelo administrador da plataforma)
# ---------------------------------------------------------------------------

class SubcategoriaInline(admin.TabularInline):
    model = Categoria
    fk_name = "categoria_pai"
    fields = ("nome", "slug", "icone", "ativa")
    prepopulated_fields = {"slug": ("nome",)}
    extra = 0
    verbose_name = "subcategoria"
    verbose_name_plural = "subcategorias"


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nome", "icone_preview", "categoria_pai", "qtd_cursos", "ativa")
    list_display_links = ("nome",)
    list_editable = ("ativa",)
    list_filter = ("ativa", TipoCategoriaFilter, ("categoria_pai", admin.RelatedOnlyFieldListFilter))
    search_fields = ("nome", "descricao")
    prepopulated_fields = {"slug": ("nome",)}
    autocomplete_fields = ("categoria_pai",)
    inlines = [SubcategoriaInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("categoria_pai").annotate(
            n_cursos=Count("cursos", distinct=True))

    @admin.display(description="ícone")
    def icone_preview(self, obj):
        if obj.icone:
            return format_html('<i class="{}"></i>', obj.icone)
        return "-"

    @admin.display(description="cursos", ordering="n_cursos")
    def qtd_cursos(self, obj):
        return obj.n_cursos


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("nome", "slug", "qtd_cursos")
    search_fields = ("nome",)
    prepopulated_fields = {"slug": ("nome",)}

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(n_cursos=Count("cursos"))

    @admin.display(description="cursos", ordering="n_cursos")
    def qtd_cursos(self, obj):
        return obj.n_cursos


# ---------------------------------------------------------------------------
# Curso, Módulo e Aula
# ---------------------------------------------------------------------------

class ModuloInline(admin.TabularInline):
    model = Modulo
    fields = ("ordem", "titulo", "descricao")
    extra = 0
    show_change_link = True  # link para editar o módulo e suas aulas


class AvaliacaoInline(admin.TabularInline):
    model = Avaliacao
    fields = ("aluno", "nota", "comentario", "aprovada", "criado_em")
    readonly_fields = ("aluno", "nota", "comentario", "criado_em")
    extra = 0
    can_delete = False
    classes = ("collapse",)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Curso)
class CursoAdmin(VendedorRestritoMixin, admin.ModelAdmin):
    list_display = ("miniatura", "titulo", "vendedor", "categoria", "nivel", "preco_formatado",
                    "status_colorido", "destaque", "qtd_alunos", "nota", "receita")
    list_display_links = ("miniatura", "titulo")
    list_filter = (
        "status", FaixaPrecoFilter, EmPromocaoFilter, NotaMediaFilter, PopularidadeFilter,
        ReceitaCursoFilter, ConteudoCursoFilter, "nivel", "idioma",
        ("categoria", admin.RelatedOnlyFieldListFilter), VendedorFilter,
        "destaque", "emite_certificado", ("criado_em", admin.DateFieldListFilter), "tags",
    )
    filtros_somente_admin = (VendedorFilter,)
    search_fields = ("titulo", "subtitulo", "descricao", "vendedor__username",
                     "vendedor__first_name", "vendedor__last_name", "categoria__nome", "tags__nome")
    date_hierarchy = "criado_em"
    list_per_page = 20
    list_select_related = ("vendedor", "categoria")
    prepopulated_fields = {"slug": ("titulo",)}
    autocomplete_fields = ("categoria", "tags", "vendedor")
    readonly_fields = ("previa_imagem", "criado_em", "atualizado_em", "publicado_em", "resumo_conteudo")
    inlines = [ModuloInline, AvaliacaoInline]
    actions = ["enviar_para_revisao", "publicar", "arquivar", "marcar_destaque", "remover_destaque",
               "duplicar", exportar_csv]
    fieldsets = (
        ("Informações principais", {
            "fields": ("titulo", "slug", "subtitulo", "vendedor", "categoria", "tags"),
        }),
        ("Descrição", {
            "fields": ("descricao", "objetivos", "requisitos"),
        }),
        ("Classificação", {
            "fields": ("nivel", "idioma", "emite_certificado"),
        }),
        ("Preço", {
            "fields": ("preco", "preco_promocional"),
        }),
        ("Mídia", {
            "fields": ("imagem", "previa_imagem", "video_apresentacao"),
        }),
        ("Publicação", {
            "fields": ("status", "destaque", "resumo_conteudo"),
        }),
        ("Datas", {
            "fields": ("criado_em", "atualizado_em", "publicado_em"),
            "classes": ("collapse",),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            n_alunos=Count("matriculas", filter=Q(matriculas__ativa=True), distinct=True),
            media_nota=Avg("avaliacoes__nota", filter=Q(avaliacoes__aprovada=True)),
            receita_total=subquery_receita_curso(),
        )

    # ----- Regras para vendedores -----
    def get_readonly_fields(self, request, obj=None):
        campos = list(super().get_readonly_fields(request, obj))
        if eh_vendedor(request):
            campos += ["vendedor", "destaque"]  # vendedor não escolhe dono nem destaque
        return campos

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        # O vendedor não publica direto: envia para revisão e o administrador publica.
        if db_field.name == "status" and eh_vendedor(request):
            kwargs["choices"] = [c for c in Curso.Status.choices if c[0] != Curso.Status.PUBLICADO]
        return super().formfield_for_choice_field(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if eh_vendedor(request) and not change:
            obj.vendedor = request.user
        super().save_model(request, obj, form, change)

    def get_actions(self, request):
        acoes = super().get_actions(request)
        if eh_vendedor(request):
            for nome in ("publicar", "marcar_destaque", "remover_destaque"):
                acoes.pop(nome, None)
        return acoes

    # ----- Colunas calculadas -----
    @admin.display(description="capa")
    def miniatura(self, obj):
        if obj.imagem:
            return format_html('<img src="{}" class="miniatura-admin" alt="">', obj.imagem.url)
        return "-"

    @admin.display(description="prévia da capa")
    def previa_imagem(self, obj):
        if obj.pk and obj.imagem:
            return format_html('<img src="{}" style="max-width:320px" class="rounded">', obj.imagem.url)
        return "-"

    @admin.display(description="preço", ordering="preco")
    def preco_formatado(self, obj):
        if obj.gratuito:
            return badge("Gratuito", "info")
        if obj.em_promocao:
            return format_html('<s class="text-muted">{}</s><br><b>{}</b>',
                               formatar_moeda(obj.preco), formatar_moeda(obj.preco_promocional))
        return formatar_moeda(obj.preco)

    @admin.display(description="status", ordering="status")
    def status_colorido(self, obj):
        return badge(obj.get_status_display(), CORES_STATUS_CURSO.get(obj.status, "secondary"))

    @admin.display(description="alunos", ordering="n_alunos")
    def qtd_alunos(self, obj):
        return obj.n_alunos

    @admin.display(description="nota", ordering="media_nota")
    def nota(self, obj):
        if obj.media_nota is None:
            return "-"
        return format_html('<span class="text-warning">★</span> {}', f"{obj.media_nota:.1f}")

    @admin.display(description="receita", ordering="receita_total")
    def receita(self, obj):
        return formatar_moeda(obj.receita_total or 0)

    @admin.display(description="resumo do conteúdo")
    def resumo_conteudo(self, obj):
        if not obj.pk:
            return "Salve o curso para adicionar módulos e aulas."
        horas, minutos = divmod(obj.duracao_total, 60)
        return f"{obj.modulos.count()} módulos · {obj.total_aulas} aulas · {horas}h{minutos:02d}min"

    # ----- Ações em massa -----
    @admin.action(description="Enviar para revisão")
    def enviar_para_revisao(self, request, queryset):
        n = queryset.filter(status=Curso.Status.RASCUNHO).update(status=Curso.Status.EM_REVISAO)
        self.message_user(request, f"{n} curso(s) enviado(s) para revisão.", messages.SUCCESS)

    @admin.action(description="Publicar cursos selecionados")
    def publicar(self, request, queryset):
        n = 0
        for curso in queryset.exclude(status=Curso.Status.PUBLICADO):
            curso.status = Curso.Status.PUBLICADO
            curso.save()  # save() preenche publicado_em
            n += 1
        self.message_user(request, f"{n} curso(s) publicado(s).", messages.SUCCESS)

    @admin.action(description="Arquivar cursos selecionados")
    def arquivar(self, request, queryset):
        n = queryset.update(status=Curso.Status.ARQUIVADO, destaque=False)
        self.message_user(request, f"{n} curso(s) arquivado(s).", messages.WARNING)

    @admin.action(description="Marcar como destaque")
    def marcar_destaque(self, request, queryset):
        n = queryset.filter(status=Curso.Status.PUBLICADO).update(destaque=True)
        self.message_user(request, f"{n} curso(s) publicado(s) marcado(s) como destaque.")

    @admin.action(description="Remover destaque")
    def remover_destaque(self, request, queryset):
        n = queryset.update(destaque=False)
        self.message_user(request, f"Destaque removido de {n} curso(s).")

    @admin.action(description="Duplicar curso (com módulos e aulas)")
    def duplicar(self, request, queryset):
        for original in queryset.prefetch_related("modulos__aulas", "tags"):
            tags = list(original.tags.all())
            modulos = list(original.modulos.all())
            copia = Curso.objects.get(pk=original.pk)
            copia.pk = None
            copia.slug = ""
            copia.titulo = f"{original.titulo} (cópia)"
            copia.status = Curso.Status.RASCUNHO
            copia.destaque = False
            copia.publicado_em = None
            copia.save()
            copia.tags.set(tags)
            for modulo in modulos:
                aulas = list(modulo.aulas.all())
                modulo.pk = None
                modulo.curso = copia
                modulo.save()
                for aula in aulas:
                    aula.pk = None
                    aula.modulo = modulo
                    aula.save()
        self.message_user(request, f"{queryset.count()} curso(s) duplicado(s) como rascunho.", messages.SUCCESS)


class AulaInline(admin.StackedInline):
    model = Aula
    fields = (("ordem", "titulo", "tipo"), ("duracao_minutos", "previa_gratuita"),
              "video_url", "arquivo", "descricao")
    extra = 0


@admin.register(Modulo)
class ModuloAdmin(VendedorRestritoMixin, admin.ModelAdmin):
    campo_vendedor = "curso__vendedor"
    filtros_somente_admin = (VendedorDoCursoFilter,)
    list_display = ("titulo", "curso", "ordem", "qtd_aulas", "duracao")
    list_filter = (("curso", admin.RelatedOnlyFieldListFilter), "curso__categoria", VendedorDoCursoFilter)
    search_fields = ("titulo", "curso__titulo")
    list_select_related = ("curso",)
    autocomplete_fields = ("curso",)
    inlines = [AulaInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            n_aulas=Count("aulas"), minutos=Sum("aulas__duracao_minutos"))

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "curso" and eh_vendedor(request):
            kwargs["queryset"] = Curso.objects.filter(vendedor=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description="aulas", ordering="n_aulas")
    def qtd_aulas(self, obj):
        return obj.n_aulas

    @admin.display(description="duração", ordering="minutos")
    def duracao(self, obj):
        return f"{obj.minutos or 0} min"


@admin.register(Aula)
class AulaAdmin(VendedorRestritoMixin, admin.ModelAdmin):
    campo_vendedor = "modulo__curso__vendedor"
    filtros_somente_admin = (VendedorDaAulaFilter,)
    list_display = ("titulo", "modulo", "curso_da_aula", "tipo", "duracao_minutos", "previa_gratuita", "ordem")
    list_editable = ("ordem", "previa_gratuita")
    list_filter = ("tipo", "previa_gratuita", DuracaoAulaFilter,
                   ("modulo__curso", admin.RelatedOnlyFieldListFilter), VendedorDaAulaFilter)
    search_fields = ("titulo", "descricao", "modulo__titulo", "modulo__curso__titulo")
    list_select_related = ("modulo", "modulo__curso")
    autocomplete_fields = ("modulo",)
    actions = ["liberar_previa", "bloquear_previa"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "modulo" and eh_vendedor(request):
            kwargs["queryset"] = Modulo.objects.filter(curso__vendedor=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description="curso", ordering="modulo__curso__titulo")
    def curso_da_aula(self, obj):
        return obj.modulo.curso

    @admin.action(description="Liberar como prévia gratuita")
    def liberar_previa(self, request, queryset):
        self.message_user(request, f"{queryset.update(previa_gratuita=True)} aula(s) liberada(s).")

    @admin.action(description="Bloquear prévia gratuita")
    def bloquear_previa(self, request, queryset):
        self.message_user(request, f"{queryset.update(previa_gratuita=False)} aula(s) bloqueada(s).")


# ---------------------------------------------------------------------------
# Matrículas, progresso e avaliações
# ---------------------------------------------------------------------------

class ProgressoAulaInline(admin.TabularInline):
    model = ProgressoAula
    fields = ("aula", "concluida", "concluida_em")
    readonly_fields = ("concluida_em",)
    autocomplete_fields = ("aula",)
    extra = 0


@admin.register(Matricula)
class MatriculaAdmin(VendedorRestritoMixin, admin.ModelAdmin):
    campo_vendedor = "curso__vendedor"
    filtros_somente_admin = (VendedorDoCursoFilter,)
    list_display = ("aluno", "curso", "data_matricula", "barra_progresso", "situacao", "ativa")
    list_filter = ("ativa", ProgressoMatriculaFilter, ("curso", admin.RelatedOnlyFieldListFilter),
                   "curso__categoria", VendedorDoCursoFilter, ("data_matricula", admin.DateFieldListFilter))
    search_fields = ("aluno__username", "aluno__email", "aluno__first_name", "curso__titulo")
    date_hierarchy = "data_matricula"
    list_select_related = ("aluno", "curso")
    autocomplete_fields = ("aluno", "curso", "pedido")
    readonly_fields = ("data_matricula",)
    inlines = [ProgressoAulaInline]
    actions = ["ativar", "desativar", exportar_csv]

    @admin.display(description="progresso")
    def barra_progresso(self, obj):
        p = obj.progresso
        return format_html(
            '<div class="progress" style="min-width:110px;height:16px">'
            '<div class="progress-bar bg-success" style="width:{}%">{}%</div></div>', p, p)

    @admin.display(description="situação", ordering="concluida_em")
    def situacao(self, obj):
        if obj.concluida:
            return badge("Concluída", "success")
        if not obj.ativa:
            return badge("Inativa", "secondary")
        return badge("Cursando", "primary")

    @admin.action(description="Ativar matrículas")
    def ativar(self, request, queryset):
        self.message_user(request, f"{queryset.update(ativa=True)} matrícula(s) ativada(s).")

    @admin.action(description="Desativar matrículas")
    def desativar(self, request, queryset):
        self.message_user(request, f"{queryset.update(ativa=False)} matrícula(s) desativada(s).")


@admin.register(Avaliacao)
class AvaliacaoAdmin(VendedorRestritoMixin, admin.ModelAdmin):
    campo_vendedor = "curso__vendedor"
    filtros_somente_admin = (VendedorDoCursoFilter,)
    list_display = ("curso", "aluno", "estrelas", "comentario_resumido", "aprovada", "criado_em")
    list_editable = ("aprovada",)
    list_filter = (EstrelasFilter, "aprovada", ComComentarioFilter,
                   ("curso", admin.RelatedOnlyFieldListFilter), VendedorDoCursoFilter,
                   ("criado_em", admin.DateFieldListFilter))
    search_fields = ("comentario", "curso__titulo", "aluno__username")
    date_hierarchy = "criado_em"
    list_select_related = ("curso", "aluno")
    autocomplete_fields = ("curso", "aluno")
    actions = ["aprovar", "reprovar"]

    @admin.display(description="nota", ordering="nota")
    def estrelas(self, obj):
        return format_html('<span class="text-warning">{}</span>{}', "★" * obj.nota, "☆" * (5 - obj.nota))

    @admin.display(description="comentário")
    def comentario_resumido(self, obj):
        return (obj.comentario[:60] + "...") if len(obj.comentario) > 60 else obj.comentario

    @admin.action(description="Aprovar avaliações")
    def aprovar(self, request, queryset):
        self.message_user(request, f"{queryset.update(aprovada=True)} avaliação(ões) aprovada(s).")

    @admin.action(description="Reprovar (ocultar do site)")
    def reprovar(self, request, queryset):
        self.message_user(request, f"{queryset.update(aprovada=False)} avaliação(ões) ocultada(s).")
