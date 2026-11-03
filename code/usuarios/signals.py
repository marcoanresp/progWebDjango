from django.contrib.auth.models import User
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from .models import Perfil
from .permissoes import configurar_grupos, sincronizar_usuario


@receiver(post_save, sender=User)
def criar_perfil_usuario(sender, instance, created, **kwargs):
    """Todo usuário novo ganha um perfil (cliente, por padrão)."""
    if created and not kwargs.get("raw"):
        Perfil.objects.get_or_create(usuario=instance)


@receiver(post_save, sender=Perfil)
def sincronizar_grupo_perfil(sender, instance, **kwargs):
    if not kwargs.get("raw"):
        sincronizar_usuario(instance)


def criar_grupos_apos_migrate(sender, **kwargs):
    """Executado automaticamente após o `migrate`: cria os grupos Vendedores e Clientes."""
    configurar_grupos()


post_migrate.connect(criar_grupos_apos_migrate, dispatch_uid="usuarios_criar_grupos")
