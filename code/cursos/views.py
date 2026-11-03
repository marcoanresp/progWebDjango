from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404
from django.views.generic import DetailView, ListView, TemplateView

from .models import Categoria, Curso, Matricula

ORDENACOES = {
    "recentes": "-publicado_em",
    "populares": "-n_alunos",
    "avaliados": "-media_nota",
    "menor_preco": "preco",
    "maior_preco": "-preco",
}


def cursos_publicados():
    """Queryset base dos cursos visíveis no site, já com nº de alunos e nota média."""
    return (Curso.objects.filter(status=Curso.Status.PUBLICADO)
            .select_related("vendedor", "categoria")
            .annotate(n_alunos=Count("matriculas", filter=Q(matriculas__ativa=True), distinct=True),
                      media_nota=Avg("avaliacoes__nota", filter=Q(avaliacoes__aprovada=True))))


def filtrar_cursos(queryset, parametros):
    """Aplica busca e filtros vindos da URL (?q=&categoria=&nivel=&preco=&ordem=)."""
    busca = parametros.get("q", "").strip()
    if busca:
        queryset = queryset.filter(Q(titulo__icontains=busca) | Q(subtitulo__icontains=busca) |
                                   Q(descricao__icontains=busca) | Q(tags__nome__icontains=busca) |
                                   Q(vendedor__first_name__icontains=busca)).distinct()
    categoria = parametros.get("categoria")
    if categoria:
        queryset = queryset.filter(Q(categoria__slug=categoria) | Q(categoria__categoria_pai__slug=categoria))
    nivel = parametros.get("nivel")
    if nivel in Curso.Nivel.values:
        queryset = queryset.filter(nivel=nivel)
    preco = parametros.get("preco")
    if preco == "gratuito":
        queryset = queryset.filter(preco=0)
    elif preco == "pago":
        queryset = queryset.filter(preco__gt=0)
    ordem = ORDENACOES.get(parametros.get("ordem", "recentes"), "-publicado_em")
    return queryset.order_by(ordem)


class PrincipalView(TemplateView):
    template_name = "principal.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["destaques"] = cursos_publicados().filter(destaque=True)[:6]
        context["recentes"] = cursos_publicados().order_by("-publicado_em")[:6]
        context["categorias"] = Categoria.objects.filter(ativa=True, categoria_pai__isnull=True)
        return context


class CursoListView(ListView):
    template_name = "cursos.html"
    context_object_name = "cursos"
    paginate_by = 12

    def get_queryset(self):
        return filtrar_cursos(cursos_publicados(), self.request.GET)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["categorias"] = Categoria.objects.filter(ativa=True)
        context["niveis"] = Curso.Nivel.choices
        context["filtros"] = self.request.GET
        return context


class CursoDetailView(DetailView):
    template_name = "curso_detalhes.html"
    context_object_name = "curso"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        return cursos_publicados().prefetch_related("modulos__aulas", "tags")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        usuario = self.request.user
        context["matriculado"] = usuario.is_authenticated and \
            Matricula.objects.filter(aluno=usuario, curso=self.object, ativa=True).exists()
        context["avaliacoes"] = self.object.avaliacoes.filter(aprovada=True).select_related("aluno")[:10]
        return context


# ----- Área do cliente (aluno) -----

class MeusCursosView(LoginRequiredMixin, ListView):
    template_name = "meus_cursos.html"
    context_object_name = "matriculas"

    def get_queryset(self):
        return (Matricula.objects.filter(aluno=self.request.user, ativa=True)
                .select_related("curso", "curso__vendedor"))


class AssistirCursoView(LoginRequiredMixin, DetailView):
    """Sala de aula: somente alunos matriculados acessam o conteúdo completo."""
    template_name = "assistir_curso.html"
    context_object_name = "matricula"

    def get_object(self, queryset=None):
        return get_object_or_404(Matricula.objects.select_related("curso"),
                                 aluno=self.request.user, curso__slug=self.kwargs["slug"], ativa=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["curso"] = self.object.curso
        context["modulos"] = self.object.curso.modulos.prefetch_related("aulas")
        context["aulas_concluidas"] = set(self.object.progressos.filter(concluida=True)
                                          .values_list("aula_id", flat=True))
        return context


# ----- Área do vendedor -----

class VendedorRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Permite acesso apenas a usuários com perfil de vendedor."""

    def test_func(self):
        perfil = getattr(self.request.user, "perfil", None)
        return perfil is not None and perfil.eh_vendedor


class PainelVendedorView(VendedorRequiredMixin, TemplateView):
    template_name = "painel_vendedor.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cursos"] = (Curso.objects.filter(vendedor=self.request.user)
                             .annotate(n_alunos=Count("matriculas", filter=Q(matriculas__ativa=True), distinct=True),
                                       media_nota=Avg("avaliacoes__nota")))
        return context
