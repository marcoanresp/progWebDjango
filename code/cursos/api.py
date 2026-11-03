"""
Endpoints JSON que serão consumidos pelo frontend em Vue.
Ex.: GET /api/cursos/?q=python&categoria=programacao&ordem=populares
"""
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from .models import Categoria
from .views import cursos_publicados, filtrar_cursos


def curso_para_dict(curso, request):
    return {
        "id": curso.id,
        "titulo": curso.titulo,
        "slug": curso.slug,
        "subtitulo": curso.subtitulo,
        "imagem": request.build_absolute_uri(curso.imagem.url) if curso.imagem else None,
        "vendedor": curso.vendedor.get_full_name() or curso.vendedor.username,
        "categoria": curso.categoria.nome,
        "nivel": curso.get_nivel_display(),
        "preco": float(curso.preco),
        "preco_atual": float(curso.preco_atual),
        "em_promocao": curso.em_promocao,
        "alunos": curso.n_alunos,
        "nota_media": round(curso.media_nota, 1) if curso.media_nota else None,
    }


def api_cursos(request):
    cursos = filtrar_cursos(cursos_publicados(), request.GET)[:50]
    return JsonResponse({"resultados": [curso_para_dict(c, request) for c in cursos]})


def api_curso_detalhes(request, slug):
    curso = get_object_or_404(cursos_publicados().prefetch_related("modulos__aulas"), slug=slug)
    dados = curso_para_dict(curso, request)
    dados.update({
        "descricao": curso.descricao,
        "objetivos": curso.objetivos,
        "requisitos": curso.requisitos,
        "duracao_minutos": curso.duracao_total,
        "tags": list(curso.tags.values_list("nome", flat=True)),
        "modulos": [
            {"titulo": m.titulo, "ordem": m.ordem,
             "aulas": [{"titulo": a.titulo, "tipo": a.get_tipo_display(), "duracao": a.duracao_minutos,
                        "previa_gratuita": a.previa_gratuita} for a in m.aulas.all()]}
            for m in curso.modulos.all()
        ],
    })
    return JsonResponse(dados)


def api_categorias(request):
    categorias = Categoria.objects.filter(ativa=True).values("id", "nome", "slug", "icone", "categoria_pai_id")
    return JsonResponse({"resultados": list(categorias)})
