from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import Aula, Avaliacao, Categoria, Curso, Matricula, Modulo, ProgressoAula


def criar_vendedor(username="prof"):
    user = User.objects.create_user(username=username, password="SenhaForte#2026", first_name="Prof")
    user.perfil.tipo = "VENDEDOR"
    user.perfil.save()
    return user


class CursoModelTestCase(TestCase):
    def setUp(self):
        self.vendedor = criar_vendedor()
        self.categoria = Categoria.objects.create(nome="Programação")
        self.curso = Curso.objects.create(titulo="Introdução ao Django", descricao="Curso de Django",
                                          vendedor=self.vendedor, categoria=self.categoria,
                                          preco=Decimal("100.00"), preco_promocional=Decimal("80.00"))
        modulo = Modulo.objects.create(curso=self.curso, titulo="Início", ordem=1)
        Aula.objects.create(modulo=modulo, titulo="Aula 1", duracao_minutos=10, ordem=1)
        Aula.objects.create(modulo=modulo, titulo="Aula 2", duracao_minutos=25, ordem=2)

    def test_slug_e_preco_atual(self):
        self.assertEqual(self.curso.slug, "introducao-ao-django")
        self.assertEqual(self.curso.preco_atual, Decimal("80.00"))
        self.assertTrue(self.curso.em_promocao)

    def test_slug_unico(self):
        outro = Curso.objects.create(titulo="Introdução ao Django", descricao="x", vendedor=self.vendedor,
                                     categoria=self.categoria, preco=10)
        self.assertEqual(outro.slug, "introducao-ao-django-2")

    def test_duracao_e_total_aulas(self):
        self.assertEqual(self.curso.total_aulas, 2)
        self.assertEqual(self.curso.duracao_total, 35)

    def test_preco_promocional_maior_que_preco_e_invalido(self):
        self.curso.preco_promocional = Decimal("150.00")
        with self.assertRaises(ValidationError):
            self.curso.full_clean()

    def test_publicar_preenche_data(self):
        self.assertIsNone(self.curso.publicado_em)
        self.curso.status = Curso.Status.PUBLICADO
        self.curso.save()
        self.assertIsNotNone(self.curso.publicado_em)

    def test_avaliacao_exige_matricula(self):
        aluno = User.objects.create_user(username="aluno", password="SenhaForte#2026")
        avaliacao = Avaliacao(curso=self.curso, aluno=aluno, nota=5)
        with self.assertRaises(ValidationError):
            avaliacao.full_clean()
        Matricula.objects.create(aluno=aluno, curso=self.curso)
        avaliacao.full_clean()  # agora é válida

    # Confirma que as regras também valem fora de formulários.
    def test_avaliacao_exige_matricula_ativa_ao_salvar(self):
        aluno = User.objects.create_user(username="aluno-inativo", email="aluno-inativo@example.com")
        Matricula.objects.create(aluno=aluno, curso=self.curso, ativa=False)
        with self.assertRaises(ValidationError):
            Avaliacao.objects.create(curso=self.curso, aluno=aluno, nota=5)

    def test_progresso_nao_pode_apontar_para_aula_de_outro_curso(self):
        aluno = User.objects.create_user(username="aluno-progresso", email="progresso@example.com")
        matricula = Matricula.objects.create(aluno=aluno, curso=self.curso)
        outro_curso = Curso.objects.create(
            titulo="Outro curso", descricao="x", vendedor=self.vendedor,
            categoria=self.categoria, preco=10)
        outro_modulo = Modulo.objects.create(curso=outro_curso, titulo="Módulo")
        outra_aula = Aula.objects.create(modulo=outro_modulo, titulo="Aula")
        with self.assertRaises(ValidationError):
            ProgressoAula.objects.create(matricula=matricula, aula=outra_aula)

    # Documenta a política escolhida: categoria inativa não retira curso publicado do catálogo.
    def test_categoria_inativa_nao_oculta_curso_publicado(self):
        self.curso.status = Curso.Status.PUBLICADO
        self.curso.save()
        self.categoria.ativa = False
        self.categoria.save()
        resposta = self.client.get(reverse("cursos"))
        self.assertContains(resposta, self.curso.titulo)


class CursoViewTestCase(TestCase):
    def setUp(self):
        vendedor = criar_vendedor()
        categoria = Categoria.objects.create(nome="Design")
        self.publicado = Curso.objects.create(titulo="Figma Essencial", descricao="x", vendedor=vendedor,
                                              categoria=categoria, preco=50, status=Curso.Status.PUBLICADO)
        self.rascunho = Curso.objects.create(titulo="Curso Secreto", descricao="x", vendedor=vendedor,
                                             categoria=categoria, preco=50)

    def test_lista_mostra_apenas_publicados(self):
        resposta = self.client.get(reverse("cursos"))
        self.assertContains(resposta, "Figma Essencial")
        self.assertNotContains(resposta, "Curso Secreto")

    def test_detalhes_de_rascunho_retorna_404(self):
        self.assertEqual(self.client.get(reverse("curso_detalhes", args=[self.rascunho.slug])).status_code, 404)
        self.assertEqual(self.client.get(reverse("curso_detalhes", args=[self.publicado.slug])).status_code, 200)

    def test_busca(self):
        resposta = self.client.get(reverse("cursos"), {"q": "figma"})
        self.assertContains(resposta, "Figma Essencial")

    def test_api_cursos(self):
        dados = self.client.get(reverse("api_cursos")).json()
        self.assertEqual(len(dados["resultados"]), 1)
        self.assertEqual(dados["resultados"][0]["titulo"], "Figma Essencial")

    def test_painel_vendedor_bloqueado_para_cliente(self):
        User.objects.create_user(username="cliente", password="SenhaForte#2026")
        self.client.login(username="cliente", password="SenhaForte#2026")
        self.assertEqual(self.client.get(reverse("painel_vendedor")).status_code, 403)
