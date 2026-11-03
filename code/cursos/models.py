from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg, Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class Categoria(models.Model):
    """Categoria de cursos. Pode ter uma categoria pai (ex.: Programação > Python)."""

    nome = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    descricao = models.TextField("descrição", blank=True)
    icone = models.CharField(max_length=50, blank=True,
                             help_text="Classe do Font Awesome. Ex.: fas fa-code")
    categoria_pai = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name="subcategorias", verbose_name="categoria pai")
    ativa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "categoria"
        verbose_name_plural = "categorias"
        ordering = ["nome"]

    def __str__(self):
        if self.categoria_pai:
            return f"{self.categoria_pai.nome} > {self.nome}"
        return self.nome

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nome)
        super().save(*args, **kwargs)


class Tag(models.Model):
    """Palavra-chave usada para facilitar a busca de cursos."""

    nome = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=60, unique=True, blank=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nome)
        super().save(*args, **kwargs)


class Curso(models.Model):
    """Infoproduto principal do site: um curso online vendido por um vendedor."""

    class Nivel(models.TextChoices):
        INICIANTE = "INICIANTE", "Iniciante"
        INTERMEDIARIO = "INTERMEDIARIO", "Intermediário"
        AVANCADO = "AVANCADO", "Avançado"
        TODOS = "TODOS", "Todos os níveis"

    class Idioma(models.TextChoices):
        PORTUGUES = "PT", "Português"
        INGLES = "EN", "Inglês"
        ESPANHOL = "ES", "Espanhol"

    class Status(models.TextChoices):
        RASCUNHO = "RASCUNHO", "Rascunho"
        EM_REVISAO = "EM_REVISAO", "Em revisão"
        PUBLICADO = "PUBLICADO", "Publicado"
        ARQUIVADO = "ARQUIVADO", "Arquivado"

    titulo = models.CharField("título", max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    subtitulo = models.CharField("subtítulo", max_length=255, blank=True)
    descricao = models.TextField("descrição")
    objetivos = models.TextField("o que o aluno vai aprender", blank=True)
    requisitos = models.TextField(blank=True)

    vendedor = models.ForeignKey(User, on_delete=models.PROTECT, related_name="cursos_vendidos",
                                 limit_choices_to={"perfil__tipo": "VENDEDOR"})
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="cursos")
    tags = models.ManyToManyField(Tag, blank=True, related_name="cursos")

    nivel = models.CharField("nível", max_length=15, choices=Nivel.choices, default=Nivel.INICIANTE)
    idioma = models.CharField(max_length=2, choices=Idioma.choices, default=Idioma.PORTUGUES)

    preco = models.DecimalField("preço", max_digits=8, decimal_places=2,
                                validators=[MinValueValidator(Decimal("0.00"))])
    preco_promocional = models.DecimalField("preço promocional", max_digits=8, decimal_places=2,
                                            null=True, blank=True,
                                            validators=[MinValueValidator(Decimal("0.00"))])

    imagem = models.ImageField("imagem de capa", upload_to="cursos/", default="cursos/capa_padrao.png")
    video_apresentacao = models.URLField("vídeo de apresentação", blank=True)

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RASCUNHO)
    destaque = models.BooleanField(default=False, help_text="Exibir na página inicial.")
    emite_certificado = models.BooleanField("emite certificado", default=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    publicado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "curso"
        verbose_name_plural = "cursos"
        ordering = ["-criado_em"]

    def __str__(self):
        return self.titulo

    def clean(self):
        if self.preco_promocional is not None and self.preco is not None \
                and self.preco_promocional >= self.preco:
            raise ValidationError({"preco_promocional": "O preço promocional deve ser menor que o preço normal."})

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.titulo)[:200]
            slug = base
            n = 2
            while Curso.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        if self.status == self.Status.PUBLICADO and self.publicado_em is None:
            self.publicado_em = timezone.now()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("curso_detalhes", args=[self.slug])

    # ----- Propriedades calculadas -----
    @property
    def preco_atual(self):
        """Preço efetivamente cobrado (promocional, se houver)."""
        if self.preco_promocional is not None:
            return self.preco_promocional
        return self.preco

    @property
    def em_promocao(self):
        return self.preco_promocional is not None

    @property
    def gratuito(self):
        return self.preco_atual == 0

    @property
    def total_aulas(self):
        return Aula.objects.filter(modulo__curso=self).count()

    @property
    def duracao_total(self):
        """Duração total do curso em minutos."""
        total = Aula.objects.filter(modulo__curso=self).aggregate(t=Sum("duracao_minutos"))["t"]
        return total or 0

    @property
    def nota_media(self):
        media = self.avaliacoes.filter(aprovada=True).aggregate(m=Avg("nota"))["m"]
        return round(media, 1) if media else None

    @property
    def total_alunos(self):
        return self.matriculas.filter(ativa=True).count()


class Modulo(models.Model):
    """Seção de um curso, que agrupa várias aulas."""

    curso = models.ForeignKey(Curso, on_delete=models.CASCADE, related_name="modulos")
    titulo = models.CharField("título", max_length=200)
    descricao = models.TextField("descrição", blank=True)
    ordem = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "módulo"
        verbose_name_plural = "módulos"
        ordering = ["curso", "ordem"]

    def __str__(self):
        return f"{self.curso.titulo} - Módulo {self.ordem}: {self.titulo}"


class Aula(models.Model):
    """Conteúdo individual de um módulo (vídeo, texto, PDF ou exercício)."""

    class Tipo(models.TextChoices):
        VIDEO = "VIDEO", "Vídeo"
        TEXTO = "TEXTO", "Texto"
        PDF = "PDF", "Material em PDF"
        EXERCICIO = "EXERCICIO", "Exercício"

    modulo = models.ForeignKey(Modulo, on_delete=models.CASCADE, related_name="aulas",
                               verbose_name="módulo")
    titulo = models.CharField("título", max_length=200)
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.VIDEO)
    descricao = models.TextField("descrição", blank=True)
    video_url = models.URLField("URL do vídeo", blank=True)
    arquivo = models.FileField(upload_to="aulas/", blank=True, null=True)
    conteudo = models.TextField("conteúdo em texto", blank=True)
    duracao_minutos = models.PositiveIntegerField("duração (min)", default=0)
    ordem = models.PositiveIntegerField(default=1)
    previa_gratuita = models.BooleanField("prévia gratuita", default=False,
                                          help_text="Permite que visitantes assistam esta aula sem comprar.")

    class Meta:
        verbose_name = "aula"
        verbose_name_plural = "aulas"
        ordering = ["modulo", "ordem"]

    def __str__(self):
        return f"{self.modulo.ordem}.{self.ordem} - {self.titulo}"

    @property
    def curso(self):
        return self.modulo.curso


class Matricula(models.Model):
    """Vínculo entre um cliente e um curso adquirido (gerado quando o pedido é pago)."""

    aluno = models.ForeignKey(User, on_delete=models.CASCADE, related_name="matriculas")
    curso = models.ForeignKey(Curso, on_delete=models.PROTECT, related_name="matriculas")
    pedido = models.ForeignKey("vendas.Pedido", on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="matriculas")
    ativa = models.BooleanField(default=True)
    data_matricula = models.DateTimeField("data da matrícula", auto_now_add=True)
    concluida_em = models.DateTimeField("concluída em", null=True, blank=True)

    class Meta:
        verbose_name = "matrícula"
        verbose_name_plural = "matrículas"
        ordering = ["-data_matricula"]
        constraints = [
            models.UniqueConstraint(fields=["aluno", "curso"], name="matricula_unica_por_aluno"),
        ]

    def __str__(self):
        return f"{self.aluno.username} em {self.curso.titulo}"

    @property
    def progresso(self):
        """Percentual (0-100) de aulas concluídas."""
        total = self.curso.total_aulas
        if total == 0:
            return 0
        concluidas = self.progressos.filter(concluida=True).count()
        return round(concluidas * 100 / total)

    @property
    def concluida(self):
        return self.concluida_em is not None


class ProgressoAula(models.Model):
    """Registra quais aulas cada aluno já concluiu."""

    matricula = models.ForeignKey(Matricula, on_delete=models.CASCADE, related_name="progressos",
                                  verbose_name="matrícula")
    aula = models.ForeignKey(Aula, on_delete=models.CASCADE, related_name="progressos")
    concluida = models.BooleanField("concluída", default=True)
    concluida_em = models.DateTimeField("concluída em", auto_now_add=True)

    class Meta:
        verbose_name = "progresso de aula"
        verbose_name_plural = "progressos de aula"
        constraints = [
            models.UniqueConstraint(fields=["matricula", "aula"], name="progresso_unico_por_aula"),
        ]

    def __str__(self):
        return f"{self.matricula.aluno.username} - {self.aula.titulo}"


class Avaliacao(models.Model):
    """Nota (1 a 5) e comentário de um aluno sobre um curso que ele comprou."""

    curso = models.ForeignKey(Curso, on_delete=models.CASCADE, related_name="avaliacoes")
    aluno = models.ForeignKey(User, on_delete=models.CASCADE, related_name="avaliacoes")
    nota = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comentario = models.TextField("comentário", blank=True)
    aprovada = models.BooleanField(default=True, help_text="Avaliações reprovadas não aparecem no site.")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "avaliação"
        verbose_name_plural = "avaliações"
        ordering = ["-criado_em"]
        constraints = [
            models.UniqueConstraint(fields=["curso", "aluno"], name="avaliacao_unica_por_aluno"),
        ]

    def __str__(self):
        return f"{self.curso.titulo} - {self.nota}★ por {self.aluno.username}"

    def clean(self):
        if self.curso_id and self.aluno_id and \
                not Matricula.objects.filter(curso_id=self.curso_id, aluno_id=self.aluno_id).exists():
            raise ValidationError("Somente alunos matriculados podem avaliar o curso.")
