from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView, TemplateView

from .filters import subquery_receita_curso
from .forms import AvaliacaoForm
from .models import Aula, Avaliacao, Categoria, Curso, Matricula, ProgressoAula

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
        destaques = list(cursos_publicados().filter(destaque=True)[:6])
        context["destaques"] = destaques
        # Lançamentos: os mais recentes que ainda não aparecem em "Em destaque"
        context["recentes"] = (cursos_publicados().exclude(pk__in=[c.pk for c in destaques])
                               .order_by("-publicado_em")[:6])

        # Categorias principais com a quantidade de cursos publicados (incluindo as subcategorias)
        categorias = list(Categoria.objects.filter(ativa=True, categoria_pai__isnull=True))
        for categoria in categorias:
            categoria.qtd_cursos = Curso.objects.filter(
                Q(categoria=categoria) | Q(categoria__categoria_pai=categoria),
                status=Curso.Status.PUBLICADO).count()
        context["categorias"] = categorias

        publicados = Curso.objects.filter(status=Curso.Status.PUBLICADO)
        context["estatisticas"] = {
            "cursos": publicados.count(),
            "alunos": Matricula.objects.filter(ativa=True).values("aluno").distinct().count(),
            "vendedores": publicados.values("vendedor").distinct().count(),
        }
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
        curso = self.object
        matriculado = usuario.is_authenticated and \
            Matricula.objects.filter(aluno=usuario, curso=curso, ativa=True).exists()
        context["matriculado"] = matriculado
        context["objetivos"] = [linha.strip() for linha in curso.objetivos.splitlines() if linha.strip()]
        context["requisitos"] = [linha.strip() for linha in curso.requisitos.splitlines() if linha.strip()]

        # Dados do instrutor (vendedor) para o cartão "Sobre o instrutor"
        cursos_do_vendedor = Curso.objects.filter(vendedor=curso.vendedor, status=Curso.Status.PUBLICADO)
        context["instrutor"] = {
            "perfil": getattr(curso.vendedor, "perfil", None),
            "cursos": cursos_do_vendedor.count(),
            "alunos": Matricula.objects.filter(curso__in=cursos_do_vendedor, ativa=True)
                                       .values("aluno").distinct().count(),
        }

        # Avaliações públicas (aprovadas). A do próprio aluno aparece separada, no formulário.
        aprovadas = curso.avaliacoes.filter(aprovada=True)
        outras = aprovadas.select_related("aluno")
        if usuario.is_authenticated:
            outras = outras.exclude(aluno=usuario)
        context["avaliacoes"] = outras[:20]
        context["resumo_avaliacoes"] = resumo_avaliacoes(aprovadas)

        # Formulário de avaliação: só para alunos matriculados
        if matriculado:
            minha = Avaliacao.objects.filter(curso=curso, aluno=usuario).first()
            context["minha_avaliacao"] = minha
            context["form_avaliacao"] = AvaliacaoForm(instance=minha)
        return context


def resumo_avaliacoes(avaliacoes):
    """Total de avaliações e quantas existem de cada nota (5 a 1), com a porcentagem para as barras."""
    contagem = dict(avaliacoes.order_by().values_list("nota").annotate(qtd=Count("id")))
    total = sum(contagem.values())
    return {
        "total": total,
        "estrelas": [
            {"nota": nota, "qtd": contagem.get(nota, 0),
             "porcentagem": round(contagem.get(nota, 0) * 100 / total) if total else 0}
            for nota in range(5, 0, -1)
        ],
    }


@login_required
@require_POST
def marcar_aula(request, slug, aula_id):
    """
    Marca (ou desmarca) uma aula como concluída para o aluno logado.
    Quando todas as aulas estão concluídas, a matrícula recebe a data de conclusão.
    """
    matricula = get_object_or_404(Matricula, aluno=request.user, curso__slug=slug, ativa=True)
    aula = get_object_or_404(Aula, pk=aula_id, modulo__curso=matricula.curso)

    progresso = ProgressoAula.objects.filter(matricula=matricula, aula=aula).first()
    if progresso:
        progresso.delete()          # já estava concluída: desmarca
    else:
        ProgressoAula.objects.create(matricula=matricula, aula=aula)

    total = matricula.curso.total_aulas
    concluidas = matricula.progressos.filter(concluida=True).count()
    if total and concluidas == total and matricula.concluida_em is None:
        matricula.concluida_em = timezone.now()
        matricula.save(update_fields=["concluida_em"])
        messages.success(request, "Parabéns! Você concluiu o curso.")
    elif concluidas < total and matricula.concluida_em is not None:
        matricula.concluida_em = None
        matricula.save(update_fields=["concluida_em"])
    return redirect(reverse("assistir_curso", args=[slug]) + f"#aula{aula.pk}")


@login_required
@require_POST
def avaliar_curso(request, slug):
    """
    Cria ou atualiza a avaliação do aluno logado.
    Regras: o curso precisa estar publicado e o aluno precisa ter uma matrícula ativa nele.
    Cada aluno tem no máximo uma avaliação por curso; enviar de novo apenas edita a existente.
    """
    curso = get_object_or_404(Curso, slug=slug, status=Curso.Status.PUBLICADO)
    destino = reverse("curso_detalhes", args=[slug]) + "#avaliar"

    if not Matricula.objects.filter(aluno=request.user, curso=curso, ativa=True).exists():
        messages.error(request, "Só alunos matriculados podem avaliar este curso.")
        return redirect("curso_detalhes", slug=slug)

    existente = Avaliacao.objects.filter(curso=curso, aluno=request.user).first()
    form = AvaliacaoForm(request.POST, instance=existente)
    if form.is_valid():
        avaliacao = form.save(commit=False)
        avaliacao.curso = curso
        avaliacao.aluno = request.user
        avaliacao.save()
        if existente:
            messages.success(request, "Sua avaliação foi atualizada.")
        else:
            messages.success(request, "Obrigado por avaliar o curso!")
    else:
        for erros in form.errors.values():
            for erro in erros:
                messages.error(request, erro)
    return redirect(destino)


@login_required
@require_POST
def excluir_avaliacao(request, slug):
    """Permite ao aluno apagar a própria avaliação."""
    apagadas, _ = Avaliacao.objects.filter(curso__slug=slug, aluno=request.user).delete()
    if apagadas:
        messages.info(request, "Sua avaliação foi removida.")
    return redirect(reverse("curso_detalhes", args=[slug]) + "#avaliar")


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
        context["minha_avaliacao"] = Avaliacao.objects.filter(curso=self.object.curso,
                                                              aluno=self.request.user).first()
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
        cursos = (Curso.objects.filter(vendedor=self.request.user)
                  .annotate(n_alunos=Count("matriculas", filter=Q(matriculas__ativa=True), distinct=True),
                            media_nota=Avg("avaliacoes__nota", filter=Q(avaliacoes__aprovada=True)),
                            receita=subquery_receita_curso()))
        context["cursos"] = cursos
        receita_bruta = sum((c.receita or Decimal("0")) for c in cursos)
        taxa = Decimal(str(settings.TAXA_PLATAFORMA))
        media = Avaliacao.objects.filter(curso__vendedor=self.request.user, aprovada=True).aggregate(m=Avg("nota"))["m"]
        context["indicadores"] = {
            "publicados": sum(1 for c in cursos if c.status == Curso.Status.PUBLICADO),
            "em_revisao": sum(1 for c in cursos if c.status == Curso.Status.EM_REVISAO),
            "alunos": sum(c.n_alunos for c in cursos),
            "receita_liquida": receita_bruta * (1 - taxa),
            "nota_media": media,
            "taxa_percentual": int(taxa * 100),
        }
        return context
