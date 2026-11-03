from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from cursos.models import Curso, Matricula


def arredondar(valor):
    return Decimal(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class Cupom(models.Model):
    """
    Cupom de desconto. Pode ser da plataforma (sem vendedor) ou de um vendedor
    específico; neste caso só vale para os cursos dele.
    """

    class Tipo(models.TextChoices):
        PERCENTUAL = "PERCENTUAL", "Percentual (%)"
        VALOR_FIXO = "VALOR_FIXO", "Valor fixo (R$)"

    codigo = models.CharField("código", max_length=30, unique=True)
    descricao = models.CharField("descrição", max_length=200, blank=True)
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.PERCENTUAL)
    valor = models.DecimalField(max_digits=8, decimal_places=2,
                                validators=[MinValueValidator(Decimal("0.01"))])
    vendedor = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True,
                                 related_name="cupons", limit_choices_to={"perfil__tipo": "VENDEDOR"},
                                 help_text="Deixe em branco para um cupom válido em toda a plataforma.")
    cursos = models.ManyToManyField(Curso, blank=True, related_name="cupons",
                                    help_text="Deixe em branco para valer em todos os cursos.")
    validade_inicio = models.DateTimeField("início da validade", default=timezone.now)
    validade_fim = models.DateTimeField("fim da validade", null=True, blank=True)
    usos_maximos = models.PositiveIntegerField("usos máximos", null=True, blank=True,
                                               help_text="Em branco = ilimitado.")
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "cupom"
        verbose_name_plural = "cupons"
        ordering = ["-criado_em"]

    def __str__(self):
        return self.codigo

    def clean(self):
        if self.tipo == self.Tipo.PERCENTUAL and self.valor and self.valor > 100:
            raise ValidationError({"valor": "Um cupom percentual não pode passar de 100%."})
        if self.validade_fim and self.validade_inicio and self.validade_fim <= self.validade_inicio:
            raise ValidationError({"validade_fim": "O fim da validade deve ser depois do início."})

    def save(self, *args, **kwargs):
        self.codigo = self.codigo.upper().strip()
        super().save(*args, **kwargs)

    @property
    def total_usos(self):
        return self.pedidos.exclude(status=Pedido.Status.CANCELADO).count()

    def esta_valido(self):
        agora = timezone.now()
        if not self.ativo or agora < self.validade_inicio:
            return False
        if self.validade_fim and agora > self.validade_fim:
            return False
        if self.usos_maximos is not None and self.total_usos >= self.usos_maximos:
            return False
        return True
    esta_valido.boolean = True
    esta_valido.short_description = "válido agora?"

    def aplica_ao_curso(self, curso):
        if self.vendedor_id and curso.vendedor_id != self.vendedor_id:
            return False
        if self.pk and self.cursos.exists() and not self.cursos.filter(pk=curso.pk).exists():
            return False
        return True

    def calcular_desconto(self, valor):
        if self.tipo == self.Tipo.PERCENTUAL:
            desconto = valor * self.valor / Decimal("100")
        else:
            desconto = self.valor
        return arredondar(min(desconto, valor))


class Pedido(models.Model):
    """Compra realizada por um cliente. Um pedido pode conter vários cursos."""

    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Aguardando pagamento"
        PAGO = "PAGO", "Pago"
        CANCELADO = "CANCELADO", "Cancelado"
        REEMBOLSADO = "REEMBOLSADO", "Reembolsado"

    class FormaPagamento(models.TextChoices):
        PIX = "PIX", "PIX"
        CARTAO = "CARTAO", "Cartão de crédito"
        BOLETO = "BOLETO", "Boleto"

    cliente = models.ForeignKey(User, on_delete=models.PROTECT, related_name="pedidos")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDENTE)
    forma_pagamento = models.CharField("forma de pagamento", max_length=10,
                                       choices=FormaPagamento.choices, default=FormaPagamento.PIX)
    parcelas = models.PositiveSmallIntegerField(default=1)
    cupom = models.ForeignKey(Cupom, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="pedidos")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    desconto = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    pago_em = models.DateTimeField("pago em", null=True, blank=True)
    observacoes = models.TextField("observações", blank=True)

    class Meta:
        verbose_name = "pedido"
        verbose_name_plural = "pedidos"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Pedido #{self.numero} - {self.cliente.username}"

    @property
    def numero(self):
        return f"{self.pk:06d}" if self.pk else "------"

    def recalcular_totais(self, salvar=True):
        """Recalcula subtotal, desconto e total a partir dos itens e do cupom."""
        subtotal = Decimal("0.00")
        desconto = Decimal("0.00")
        cupom_valido = self.cupom and self.cupom.esta_valido()
        for item in self.itens.select_related("curso"):
            item.desconto = Decimal("0.00")
            if cupom_valido and self.cupom.aplica_ao_curso(item.curso):
                item.desconto = self.cupom.calcular_desconto(item.preco_unitario)
            item.save(update_fields=["desconto"])
            subtotal += item.preco_unitario
            desconto += item.desconto
        self.subtotal = arredondar(subtotal)
        self.desconto = arredondar(desconto)
        self.total = arredondar(subtotal - desconto)
        if salvar:
            self.save(update_fields=["subtotal", "desconto", "total"])

    @transaction.atomic
    def confirmar_pagamento(self):
        """Marca o pedido como pago e libera o acesso (matrícula) aos cursos comprados."""
        if self.status == self.Status.PAGO:
            return
        self.status = self.Status.PAGO
        self.pago_em = timezone.now()
        self.save(update_fields=["status", "pago_em"])
        self.liberar_acesso()

    def liberar_acesso(self):
        """Cria (ou reativa) a matrícula do cliente em cada curso do pedido."""
        for item in self.itens.select_related("curso"):
            matricula, criada = Matricula.objects.get_or_create(
                aluno=self.cliente, curso=item.curso, defaults={"pedido": self})
            if not criada and not matricula.ativa:
                matricula.ativa = True
                matricula.pedido = self
                matricula.save(update_fields=["ativa", "pedido"])

    @transaction.atomic
    def cancelar(self, reembolso=False):
        """Cancela/reembolsa o pedido e desativa as matrículas geradas por ele."""
        self.status = self.Status.REEMBOLSADO if reembolso else self.Status.CANCELADO
        self.save(update_fields=["status"])
        self.matriculas.update(ativa=False)


class ItemPedido(models.Model):
    """Curso incluído em um pedido, com o preço praticado no momento da compra."""

    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="itens")
    curso = models.ForeignKey(Curso, on_delete=models.PROTECT, related_name="itens_vendidos")
    preco_unitario = models.DecimalField("preço unitário", max_digits=8, decimal_places=2, blank=True)
    desconto = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    class Meta:
        verbose_name = "item do pedido"
        verbose_name_plural = "itens do pedido"
        constraints = [
            models.UniqueConstraint(fields=["pedido", "curso"], name="curso_unico_por_pedido"),
        ]

    def __str__(self):
        return f"{self.curso.titulo} (R$ {self.preco_unitario})"

    def save(self, *args, **kwargs):
        if self.preco_unitario is None:
            self.preco_unitario = self.curso.preco_atual
        super().save(*args, **kwargs)

    @property
    def valor_final(self):
        return arredondar(self.preco_unitario - self.desconto)

    @property
    def valor_vendedor(self):
        """Valor repassado ao vendedor após a taxa da plataforma."""
        taxa = Decimal(str(settings.TAXA_PLATAFORMA))
        return arredondar(self.valor_final * (1 - taxa))
