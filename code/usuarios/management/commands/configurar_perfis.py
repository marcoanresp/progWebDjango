from django.core.management.base import BaseCommand

from usuarios.models import Perfil
from usuarios.permissoes import configurar_grupos, sincronizar_usuario


class Command(BaseCommand):
    help = "Cria/atualiza os grupos Vendedores e Clientes e sincroniza todos os perfis."

    def handle(self, *args, **options):
        for grupo, qtd in configurar_grupos().items():
            self.stdout.write(f"Grupo '{grupo}': {qtd} permissões")
        for perfil in Perfil.objects.select_related("usuario"):
            sincronizar_usuario(perfil)
        self.stdout.write(self.style.SUCCESS("Perfis sincronizados com sucesso!"))
