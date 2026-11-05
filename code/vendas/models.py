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
        # Evita persistir cupons percentuais acima de 100% ou com validade invertida.
        self.full_clean()
        super().save(*args, **kwargs)

    def contar_usos(self, excluir_pedido_id=None):
        # Pedidos pendentes reservam uma utilização; cancelados e reembolsados a liberam.
        pedidos = self.pedidos.filter(status__in=[Pedido.Status.PENDENTE, Pedido.Status.PAGO])
        if excluir_pedido_id is not None:
            pedidos = pedidos.exclude(pk=excluir_pedido_id)
        return pedidos.count()

    @property
    def total_usos(self):
        return self.contar_usos()

    def esta_valido(self, excluir_pedido_id=None):
        agora = timezone.now()
        if not self.ativo or agora < self.validade_inicio:
            return False
        if self.validade_fim and agora > self.validade_fim:
            return False
        if self.usos_maximos is not None and \
                self.contar_usos(excluir_pedido_id=excluir_pedido_id) >= self.usos_maximos:
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

    def save(self, *args, **kwargs):
        # Mudanças de status só podem ocorrer pelos métodos que aplicam as transições do pedido.
        if self.pk and not getattr(self, "_transicao_status_autorizada", False):
            status_original = Pedido.objects.filter(pk=self.pk).values_list("status", flat=True).first()
            if status_original is not None and status_original != self.status:
                raise ValidationError({"status": "Use as ações de pagamento, cancelamento ou reembolso."})
        super().save(*args, **kwargs)

    def _salvar_transicao_status(self, *campos):
        # Autoriza temporariamente a mudança de estado após a validação de cada operação.
        self._transicao_status_autorizada = True
        try:
            self.save(update_fields=campos)
        finally:
            self._transicao_status_autorizada = False

    def recalcular_totais(self, salvar=True):
        """Soma os valores já registrados, sem alterar os preços congelados do pedido."""
        subtotal = Decimal("0.00")
        desconto = Decimal("0.00")
        for item in self.itens.all():
            subtotal += item.preco_unitario
            desconto += item.desconto
        self.subtotal = arredondar(subtotal)
        self.desconto = arredondar(desconto)
        self.total = arredondar(subtotal - desconto)
        if salvar:
            self.save(update_fields=["subtotal", "desconto", "total"])

    @transaction.atomic
    def aplicar_cupom(self, cupom):
        # Valida e reserva o cupom sob bloqueio, persistindo o desconto para manter o preço acordado.
        pedido = Pedido.objects.select_for_update().get(pk=self.pk)
        if pedido.status != self.Status.PENDENTE:
            raise ValidationError("Só é possível aplicar cupom a um pedido pendente.")
        cupom = Cupom.objects.select_for_update().get(pk=cupom.pk)
        if not cupom.esta_valido(excluir_pedido_id=pedido.pk):
            raise ValidationError("Cupom inválido, expirado ou sem usos disponíveis.")

        itens = list(pedido.itens.select_related("curso"))
        itens_aplicaveis = [item for item in itens if cupom.aplica_ao_curso(item.curso)]
        if not itens_aplicaveis:
            raise ValidationError("Este cupom não é válido para os cursos do pedido.")

        pedido.cupom = cupom
        pedido.save(update_fields=["cupom"])
        for item in itens:
            item.desconto = (cupom.calcular_desconto(item.preco_unitario)
                             if item in itens_aplicaveis else Decimal("0.00"))
            item.save(update_fields=["desconto"])
        pedido.recalcular_totais()
        self.cupom = pedido.cupom
        self.subtotal = pedido.subtotal
        self.desconto = pedido.desconto
        self.total = pedido.total

    @transaction.atomic
    def confirmar_pagamento(self):
        """Confirma somente pedidos pendentes; repetições da confirmação são idempotentes."""
        pedido = Pedido.objects.select_for_update().get(pk=self.pk)
        if pedido.status == self.Status.PAGO:
            self.status = pedido.status
            self.pago_em = pedido.pago_em
            return
        if pedido.status != self.Status.PENDENTE:
            raise ValidationError("Somente pedidos pendentes podem ser pagos.")
        if not pedido.itens.exists():
            raise ValidationError("Não é possível confirmar um pedido sem itens.")
        pedido.status = self.Status.PAGO
        pedido.pago_em = timezone.now()
        pedido._salvar_transicao_status("status", "pago_em")
        pedido.liberar_acesso()
        self.status = pedido.status
        self.pago_em = pedido.pago_em

    def liberar_acesso(self):
        """Cria (ou reativa) a matrícula do cliente em cada curso do pedido."""
        # Matrículas só podem ser liberadas depois da confirmação do pagamento.
        if self.status != self.Status.PAGO:
            raise ValidationError("O acesso só pode ser liberado para pedidos pagos.")
        for item in self.itens.select_related("curso"):
            matricula, criada = Matricula.objects.get_or_create(
                aluno=self.cliente, curso=item.curso, defaults={"pedido": self})
            if not criada and not matricula.ativa:
                matricula.ativa = True
                matricula.pedido = self
                matricula.save(update_fields=["ativa", "pedido"])

    @transaction.atomic
    def cancelar(self, reembolso=False):
        """Aplica apenas as transições pendente→cancelado e pago→reembolsado."""
        pedido = Pedido.objects.select_for_update().get(pk=self.pk)
        if pedido.status == self.Status.CANCELADO and not reembolso:
            self.status = pedido.status
            return
        if pedido.status == self.Status.REEMBOLSADO and reembolso:
            self.status = pedido.status
            return
        if reembolso and pedido.status != self.Status.PAGO:
            raise ValidationError("Somente pedidos pagos podem ser reembolsados.")
        if not reembolso and pedido.status != self.Status.PENDENTE:
            raise ValidationError("Pedidos pagos só podem ser encerrados por reembolso.")

        pedido.status = self.Status.REEMBOLSADO if reembolso else self.Status.CANCELADO
        pedido._salvar_transicao_status("status")
        pedido.matriculas.update(ativa=False)
        self.status = pedido.status


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

    def clean(self):
        # Descontos nunca podem tornar o item negativo nem exceder o preço registrado.
        if self.preco_unitario is not None and self.preco_unitario < 0:
            raise ValidationError({"preco_unitario": "O preço não pode ser negativo."})
        if self.desconto is not None and self.desconto < 0:
            raise ValidationError({"desconto": "O desconto não pode ser negativo."})
        if self.preco_unitario is not None and self.desconto is not None and \
                self.desconto > self.preco_unitario:
            raise ValidationError({"desconto": "O desconto não pode superar o preço do item."})

    def __str__(self):
        return f"{self.curso.titulo} (R$ {self.preco_unitario})"

    def save(self, *args, **kwargs):
        # O preço é copiado do curso apenas na criação e validado antes de persistir o item.
        if self._state.adding and self.preco_unitario is None:
            self.preco_unitario = self.curso.preco_atual
        if not self._state.adding:
            valores_originais = ItemPedido.objects.filter(pk=self.pk).values(
                "curso_id", "preco_unitario").first()
            if valores_originais and (
                    valores_originais["curso_id"] != self.curso_id or
                    valores_originais["preco_unitario"] != self.preco_unitario):
                raise ValidationError("O curso e o preço original do item não podem ser alterados.")
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def valor_final(self):
        return arredondar(self.preco_unitario - self.desconto)

    @property
    def valor_vendedor(self):
        """Valor repassado ao vendedor após a taxa da plataforma."""
        taxa = Decimal(str(settings.TAXA_PLATAFORMA))
        return arredondar(self.valor_final * (1 - taxa))
