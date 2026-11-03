from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from cursos.models import Categoria, Curso, Matricula

from .models import Cupom, ItemPedido, Pedido


class PedidoTestCase(TestCase):
    def setUp(self):
        self.vendedor = User.objects.create_user(username="prof", password="SenhaForte#2026")
        self.vendedor.perfil.tipo = "VENDEDOR"
        self.vendedor.perfil.save()
        self.outro_vendedor = User.objects.create_user(username="prof2", password="SenhaForte#2026")
        self.outro_vendedor.perfil.tipo = "VENDEDOR"
        self.outro_vendedor.perfil.save()
        self.cliente = User.objects.create_user(username="cliente", password="SenhaForte#2026")
        categoria = Categoria.objects.create(nome="Programação")
        self.curso1 = Curso.objects.create(titulo="Python", descricao="x", vendedor=self.vendedor,
                                           categoria=categoria, preco=Decimal("100.00"), status="PUBLICADO")
        self.curso2 = Curso.objects.create(titulo="Vue", descricao="x", vendedor=self.outro_vendedor,
                                           categoria=categoria, preco=Decimal("200.00"),
                                           preco_promocional=Decimal("150.00"), status="PUBLICADO")
        self.pedido = Pedido.objects.create(cliente=self.cliente)
        ItemPedido.objects.create(pedido=self.pedido, curso=self.curso1)
        ItemPedido.objects.create(pedido=self.pedido, curso=self.curso2)

    def test_totais_usam_preco_atual(self):
        self.pedido.recalcular_totais()
        self.assertEqual(self.pedido.total, Decimal("250.00"))

    def test_cupom_percentual_da_plataforma(self):
        self.pedido.cupom = Cupom.objects.create(codigo="dez", tipo="PERCENTUAL", valor=10)
        self.pedido.recalcular_totais()
        self.assertEqual(self.pedido.cupom.codigo, "DEZ")
        self.assertEqual(self.pedido.desconto, Decimal("25.00"))
        self.assertEqual(self.pedido.total, Decimal("225.00"))

    def test_cupom_de_vendedor_vale_so_para_os_cursos_dele(self):
        self.pedido.cupom = Cupom.objects.create(codigo="PROF30", tipo="VALOR_FIXO", valor=30,
                                                 vendedor=self.vendedor)
        self.pedido.recalcular_totais()
        self.assertEqual(self.pedido.desconto, Decimal("30.00"))
        self.assertEqual(self.pedido.total, Decimal("220.00"))

    def test_confirmar_pagamento_cria_matriculas_e_cancelar_remove_acesso(self):
        self.pedido.confirmar_pagamento()
        self.assertEqual(self.pedido.status, Pedido.Status.PAGO)
        self.assertEqual(Matricula.objects.filter(aluno=self.cliente, ativa=True).count(), 2)
        self.pedido.cancelar(reembolso=True)
        self.assertEqual(self.pedido.status, Pedido.Status.REEMBOLSADO)
        self.assertEqual(Matricula.objects.filter(aluno=self.cliente, ativa=True).count(), 0)

    def test_fluxo_de_compra_pelo_site(self):
        self.client.login(username="cliente", password="SenhaForte#2026")
        resposta = self.client.post(reverse("comprar", args=[self.curso1.slug]))
        pedido = Pedido.objects.filter(cliente=self.cliente).latest("pk")
        self.assertRedirects(resposta, reverse("pedido_detalhes", args=[pedido.pk]))
        self.client.post(reverse("pagar", args=[pedido.pk]), {"forma_pagamento": "CARTAO"})
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.PAGO)
        self.assertTrue(Matricula.objects.filter(aluno=self.cliente, curso=self.curso1).exists())


class AdminVendedorTestCase(TestCase):
    """O vendedor só enxerga os próprios cursos no ambiente administrativo."""

    def setUp(self):
        categoria = Categoria.objects.create(nome="Design")
        self.vendedores = []
        for nome in ("v1", "v2"):
            user = User.objects.create_user(username=nome, password="SenhaForte#2026")
            user.perfil.tipo = "VENDEDOR"
            user.perfil.save()
            Curso.objects.create(titulo=f"Curso de {nome}", descricao="x", vendedor=user,
                                 categoria=categoria, preco=10)
            self.vendedores.append(user)
        User.objects.create_superuser("admin", "a@a.com", "SenhaForte#2026")

    def test_vendedor_ve_apenas_seus_cursos(self):
        self.client.login(username="v1", password="SenhaForte#2026")
        resposta = self.client.get("/admin/cursos/curso/")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Curso de v1")
        self.assertNotContains(resposta, "Curso de v2")

    def test_admin_ve_tudo_e_filtros_funcionam(self):
        self.client.login(username="admin", password="SenhaForte#2026")
        for url in ["/admin/", "/admin/cursos/curso/?faixa_preco=ate50&nota=sem&alunos=0&receita=0",
                    "/admin/vendas/pedido/?valor=ate100&com_cupom=nao&qtd_itens=1",
                    "/admin/vendas/cupom/?situacao=valido", "/admin/auth/user/?tipo=VENDEDOR&compras=nenhuma",
                    "/admin/usuarios/perfil/?atividade=sem_cursos&completo=nao",
                    "/admin/cursos/matricula/?progresso=nao_iniciado", "/admin/cursos/aula/?duracao=curta",
                    "/admin/cursos/avaliacao/?estrelas=5&comentario=sim", "/admin/cursos/categoria/?hierarquia=sub"]:
            resposta = self.client.get(url)
            self.assertEqual(resposta.status_code, 200, url)
        self.assertContains(self.client.get("/admin/cursos/curso/"), "Curso de v2")
