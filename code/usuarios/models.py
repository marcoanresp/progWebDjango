from django.db import models
from django.contrib.auth.models import User


class Perfil(models.Model):
    """
    Dados complementares do usuário do Django (auth.User).
    Todo usuário cadastrado no site possui um perfil, que define se ele é
    um CLIENTE (compra cursos) ou um VENDEDOR (cria e vende cursos).
    """

    class Tipo(models.TextChoices):
        CLIENTE = "CLIENTE", "Cliente"
        VENDEDOR = "VENDEDOR", "Vendedor"

    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name="perfil")
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.CLIENTE)
    foto = models.ImageField(upload_to="perfis/", blank=True, null=True)
    bio = models.TextField("biografia", blank=True)
    telefone = models.CharField(max_length=20, blank=True)
    data_nascimento = models.DateField("data de nascimento", blank=True, null=True)

    # Campos usados apenas por vendedores
    titulo_profissional = models.CharField(
        "título profissional", max_length=120, blank=True,
        help_text="Ex.: Desenvolvedor Python, Designer UX, Professor de Matemática",
    )
    site = models.URLField(blank=True)
    chave_pix = models.CharField("chave PIX", max_length=120, blank=True,
                                 help_text="Chave usada para repasse das vendas ao vendedor.")
    verificado = models.BooleanField(default=False,
                                     help_text="Vendedor com identidade verificada pela plataforma.")

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "perfil"
        verbose_name_plural = "perfis"
        ordering = ["usuario__username"]

    def __str__(self):
        return f"{self.usuario.get_full_name() or self.usuario.username} ({self.get_tipo_display()})"

    @property
    def eh_vendedor(self):
        return self.tipo == self.Tipo.VENDEDOR

    @property
    def eh_cliente(self):
        return self.tipo == self.Tipo.CLIENTE
