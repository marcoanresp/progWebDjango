from django.apps import AppConfig


class UsuariosConfig(AppConfig):
    name = "usuarios"
    verbose_name = "Usuários e Perfis"

    def ready(self):
        from . import signals  # noqa: F401  (registra os sinais)
