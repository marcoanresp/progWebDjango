from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Perfil
from .permissoes import GRUPO_CLIENTES, GRUPO_VENDEDORES


class PerfilTestCase(TestCase):
    def test_usuario_novo_ganha_perfil_de_cliente(self):
        user = User.objects.create_user(username="joao", password="SenhaForte#2026")
        self.assertEqual(user.perfil.tipo, Perfil.Tipo.CLIENTE)
        self.assertTrue(user.groups.filter(name=GRUPO_CLIENTES).exists())
        self.assertFalse(user.is_staff)

    def test_vendedor_acessa_admin_e_entra_no_grupo(self):
        user = User.objects.create_user(username="maria", password="SenhaForte#2026")
        user.perfil.tipo = Perfil.Tipo.VENDEDOR
        user.perfil.save()
        user.refresh_from_db()
        self.assertTrue(user.is_staff)
        self.assertTrue(user.groups.filter(name=GRUPO_VENDEDORES).exists())
        self.assertFalse(user.groups.filter(name=GRUPO_CLIENTES).exists())


class CadastroViewTestCase(TestCase):
    def test_cadastro_como_vendedor(self):
        resposta = self.client.post(reverse("cadastro"), {
            "usuario": "novo.vendedor", "nome": "Novo Vendedor", "email": "nv@email.com",
            "senha": "SenhaForte#2026", "confirmacao": "SenhaForte#2026", "tipo": "VENDEDOR"})
        self.assertRedirects(resposta, reverse("painel_vendedor"))
        user = User.objects.get(username="novo.vendedor")
        self.assertTrue(user.perfil.eh_vendedor)
        self.assertEqual(user.first_name, "Novo")

    def test_cadastro_senhas_diferentes(self):
        resposta = self.client.post(reverse("cadastro"), {
            "usuario": "x", "email": "x@email.com", "senha": "SenhaForte#2026", "confirmacao": "outra"})
        self.assertContains(resposta, "As senhas não conferem")
        self.assertFalse(User.objects.filter(username="x").exists())

    def test_login_e_area_protegida(self):
        User.objects.create_user(username="aluno", password="SenhaForte#2026")
        self.assertEqual(self.client.get(reverse("meus_cursos")).status_code, 302)  # redireciona p/ login
        self.client.post(reverse("login"), {"usuario": "aluno", "senha": "SenhaForte#2026"})
        self.assertEqual(self.client.get(reverse("meus_cursos")).status_code, 200)
