"""
Popula o banco de dados com dados fictícios para testar o site e o ambiente administrativo.

Execute (dentro da pasta code, com o ambiente virtual ativo):
    python3 scripts-bd/popula_bd.py

Usuários criados (senha de todos: edumarket123):
    admin       -> administrador da plataforma (superusuário)
    ana.prof, bruno.dev, carla.design, diego.mkt, elisa.lang -> vendedores
    cliente01 ... cliente30 -> clientes
"""
import os
import random
import sys
import unicodedata
from datetime import timedelta
from decimal import Decimal

import django

# Caminho base do projeto (um nível acima da pasta scripts-bd)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portal_cursos.settings")
django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth.models import User  # noqa: E402
from django.utils import timezone  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from cursos.models import Aula, Avaliacao, Categoria, Curso, Matricula, Modulo, ProgressoAula, Tag  # noqa: E402
from usuarios.models import Perfil  # noqa: E402
from usuarios.permissoes import configurar_grupos  # noqa: E402
from vendas.models import Cupom, ItemPedido, Pedido  # noqa: E402

random.seed(42)
SENHA = "edumarket123"
agora = timezone.now()


# ---------------------------------------------------------------------------
# Imagens de capa
# ---------------------------------------------------------------------------
CORES = {
    "programacao": (44, 123, 229), "design": (214, 51, 132), "marketing-digital": (253, 126, 20),
    "negocios": (32, 135, 90), "idiomas": (111, 66, 193), "fotografia": (52, 58, 64),
}


FONTES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",            # Ubuntu/Debian
    "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",          # Fedora
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",                                    # Windows
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",               # macOS
]


def carregar_fonte(tamanho):
    for caminho in FONTES:
        if os.path.exists(caminho):
            return ImageFont.truetype(caminho, tamanho)
    return None


def gerar_capa(nome_arquivo, titulo, cor):
    """Cria uma imagem 640x360 com a cor da categoria e o título do curso."""
    pasta = os.path.join(settings.MEDIA_ROOT, "cursos")
    os.makedirs(pasta, exist_ok=True)
    caminho = os.path.join(pasta, nome_arquivo)
    img = Image.new("RGB", (640, 360), cor)
    desenho = ImageDraw.Draw(img)
    for i in range(360):  # degradê simples
        fator = i / 360 * 0.35
        desenho.line([(0, i), (640, i)], fill=tuple(int(c * (1 - fator)) for c in cor))
    fonte = carregar_fonte(34)
    if fonte is None:  # sem fonte TrueType: usa a fonte padrão e remove acentos que ela não suporta
        fonte = ImageFont.load_default()
        titulo = unicodedata.normalize("NFKD", titulo).encode("ascii", "ignore").decode()
    palavras, linhas, linha = titulo.split(), [], ""
    for palavra in palavras:
        teste = f"{linha} {palavra}".strip()
        if desenho.textlength(teste, font=fonte) > 560:
            linhas.append(linha)
            linha = palavra
        else:
            linha = teste
    linhas.append(linha)
    y = 180 - len(linhas) * 22
    for texto in linhas:
        desenho.text((40, y), texto, fill="white", font=fonte)
        y += 44
    img.save(caminho)
    return f"cursos/{nome_arquivo}"


gerar_capa("capa_padrao.png", "EduMarket", (108, 117, 125))

# ---------------------------------------------------------------------------
# Grupos, administrador, vendedores e clientes
# ---------------------------------------------------------------------------
configurar_grupos()

if not User.objects.filter(username="admin").exists():
    User.objects.create_superuser("admin", "admin@edumarket.com", SENHA, first_name="Administrador")

vendedores_dados = [
    ("ana.prof", "Ana", "Ribeiro", "Professora de Python e Ciência de Dados"),
    ("bruno.dev", "Bruno", "Martins", "Desenvolvedor Web Full Stack"),
    ("carla.design", "Carla", "Souza", "Designer UX/UI"),
    ("diego.mkt", "Diego", "Almeida", "Especialista em Marketing Digital"),
    ("elisa.lang", "Elisa", "Fernandes", "Professora de Inglês e Espanhol"),
]
vendedores = {}
for username, nome, sobrenome, titulo in vendedores_dados:
    user, criado = User.objects.get_or_create(username=username, defaults={
        "first_name": nome, "last_name": sobrenome, "email": f"{username}@edumarket.com"})
    if criado:
        user.set_password(SENHA)
        user.save()
    perfil = user.perfil
    perfil.tipo = Perfil.Tipo.VENDEDOR
    perfil.titulo_profissional = titulo
    perfil.bio = f"{nome} {sobrenome} é {titulo.lower()} com mais de 8 anos de experiência."
    perfil.chave_pix = f"{username}@edumarket.com"
    perfil.verificado = username != "elisa.lang"
    perfil.save()
    vendedores[username] = user

nomes = ["Lucas", "Mariana", "Pedro", "Julia", "Rafael", "Beatriz", "Gabriel", "Larissa", "Thiago", "Camila",
         "Felipe", "Isabela", "Rodrigo", "Patrícia", "André", "Fernanda", "Gustavo", "Letícia", "Vinícius", "Natália",
         "Caio", "Amanda", "Eduardo", "Sofia", "Henrique", "Paula", "Marcelo", "Renata", "Igor", "Helena"]
sobrenomes = ["Silva", "Santos", "Oliveira", "Pereira", "Costa", "Rodrigues", "Lima", "Gomes", "Carvalho", "Rocha"]
clientes = []
for i, nome in enumerate(nomes, start=1):
    username = f"cliente{i:02d}"
    user, criado = User.objects.get_or_create(username=username, defaults={
        "first_name": nome, "last_name": random.choice(sobrenomes), "email": f"{username}@email.com"})
    if criado:
        user.set_password(SENHA)
        user.save()
        User.objects.filter(pk=user.pk).update(date_joined=agora - timedelta(days=random.randint(5, 200)))
    clientes.append(user)

# ---------------------------------------------------------------------------
# Categorias e tags
# ---------------------------------------------------------------------------
categorias_dados = {
    ("Programação", "fas fa-code"): ["Python", "Desenvolvimento Web", "Banco de Dados"],
    ("Design", "fas fa-palette"): ["UX/UI", "Design Gráfico"],
    ("Marketing Digital", "fas fa-bullhorn"): ["Redes Sociais", "SEO"],
    ("Negócios", "fas fa-briefcase"): ["Empreendedorismo", "Finanças"],
    ("Idiomas", "fas fa-language"): ["Inglês", "Espanhol"],
    ("Fotografia", "fas fa-camera"): [],
}
categorias = {}
for (nome, icone), subcategorias in categorias_dados.items():
    pai, _ = Categoria.objects.get_or_create(nome=nome, defaults={"icone": icone})
    categorias[nome] = pai
    for sub in subcategorias:
        categorias[sub], _ = Categoria.objects.get_or_create(nome=sub, defaults={"categoria_pai": pai, "icone": icone})

tags = {}
for nome in ["Python", "Django", "JavaScript", "Vue", "SQL", "Figma", "Instagram", "Excel", "Carreira",
             "Iniciantes", "Projetos práticos", "Conversação", "Lightroom", "Google Ads"]:
    tags[nome], _ = Tag.objects.get_or_create(nome=nome)

# ---------------------------------------------------------------------------
# Cursos, módulos e aulas
# ---------------------------------------------------------------------------
cursos_dados = [
    # (título, vendedor, categoria, nível, preço, promo, status, destaque, tags)
    ("Python do Zero ao Avançado", "ana.prof", "Python", "INICIANTE", "197.00", "97.00", "PUBLICADO", True, ["Python", "Iniciantes"]),
    ("Análise de Dados com Pandas", "ana.prof", "Python", "INTERMEDIARIO", "149.90", None, "PUBLICADO", True, ["Python", "Projetos práticos"]),
    ("Machine Learning na Prática", "ana.prof", "Python", "AVANCADO", "349.00", "279.00", "PUBLICADO", False, ["Python"]),
    ("Lógica de Programação Gratuita", "ana.prof", "Programação", "INICIANTE", "0.00", None, "PUBLICADO", False, ["Iniciantes"]),
    ("Estatística para Ciência de Dados", "ana.prof", "Python", "INTERMEDIARIO", "129.00", None, "EM_REVISAO", False, ["Python"]),
    ("Django Completo: do Básico ao Deploy", "bruno.dev", "Desenvolvimento Web", "INTERMEDIARIO", "249.00", "179.00", "PUBLICADO", True, ["Django", "Python", "Projetos práticos"]),
    ("Vue.js 3 para Iniciantes", "bruno.dev", "Desenvolvimento Web", "INICIANTE", "119.00", None, "PUBLICADO", True, ["Vue", "JavaScript"]),
    ("JavaScript Moderno", "bruno.dev", "Desenvolvimento Web", "TODOS", "89.90", None, "PUBLICADO", False, ["JavaScript", "Iniciantes"]),
    ("SQL e Modelagem de Banco de Dados", "bruno.dev", "Banco de Dados", "INICIANTE", "99.00", None, "PUBLICADO", False, ["SQL"]),
    ("APIs REST com Django", "bruno.dev", "Desenvolvimento Web", "AVANCADO", "199.00", None, "RASCUNHO", False, ["Django"]),
    ("Figma Essencial", "carla.design", "UX/UI", "INICIANTE", "79.90", None, "PUBLICADO", True, ["Figma", "Iniciantes"]),
    ("UX Research na Prática", "carla.design", "UX/UI", "INTERMEDIARIO", "159.00", "129.00", "PUBLICADO", False, ["Figma", "Carreira"]),
    ("Identidade Visual para Marcas", "carla.design", "Design Gráfico", "TODOS", "139.00", None, "PUBLICADO", False, ["Projetos práticos"]),
    ("Marketing no Instagram", "diego.mkt", "Redes Sociais", "INICIANTE", "67.00", None, "PUBLICADO", False, ["Instagram"]),
    ("Google Ads Descomplicado", "diego.mkt", "Marketing Digital", "INTERMEDIARIO", "189.00", "149.00", "PUBLICADO", False, ["Google Ads"]),
    ("SEO para Iniciantes", "diego.mkt", "SEO", "INICIANTE", "59.90", None, "PUBLICADO", False, ["Iniciantes"]),
    ("Planejamento Financeiro Pessoal", "diego.mkt", "Finanças", "TODOS", "49.90", None, "ARQUIVADO", False, ["Excel"]),
    ("Inglês para Conversação", "elisa.lang", "Inglês", "INTERMEDIARIO", "129.00", None, "PUBLICADO", True, ["Conversação"]),
    ("Espanhol Básico", "elisa.lang", "Espanhol", "INICIANTE", "89.00", "69.00", "PUBLICADO", False, ["Conversação", "Iniciantes"]),
    ("Inglês para Entrevistas de Emprego", "elisa.lang", "Inglês", "AVANCADO", "99.00", None, "EM_REVISAO", False, ["Carreira"]),
    ("Fotografia com o Celular", "carla.design", "Fotografia", "INICIANTE", "0.00", None, "PUBLICADO", False, ["Lightroom", "Iniciantes"]),
]

titulos_modulos = ["Introdução", "Fundamentos", "Aprofundando", "Projeto prático", "Conclusão"]
tipos_aula = ["VIDEO", "VIDEO", "VIDEO", "TEXTO", "PDF", "EXERCICIO"]
cursos = []
for titulo, vend, cat, nivel, preco, promo, status, destaque, lista_tags in cursos_dados:
    curso = Curso.objects.filter(titulo=titulo).first()
    if curso:
        cursos.append(curso)
        continue
    categoria = categorias[cat]
    raiz = categoria.categoria_pai or categoria
    curso = Curso(
        titulo=titulo, vendedor=vendedores[vend], categoria=categoria, nivel=nivel,
        subtitulo=f"Aprenda {titulo.lower()} com exemplos reais e exercícios",
        descricao=f"Neste curso você vai dominar {titulo.lower()} passo a passo, com aulas práticas "
                  f"e materiais de apoio para download.",
        objetivos="Entender os conceitos principais\nAplicar o conteúdo em projetos reais\nGanhar confiança para o mercado",
        requisitos="Computador com acesso à internet e vontade de aprender.",
        preco=Decimal(preco), preco_promocional=Decimal(promo) if promo else None,
        status=status, destaque=destaque,
        idioma="EN" if titulo.startswith("Inglês") else "PT",
    )
    curso.save()
    curso.imagem = gerar_capa(f"{curso.slug}.png", titulo, CORES.get(raiz.slug, (108, 117, 125)))
    curso.save()
    curso.tags.set([tags[t] for t in lista_tags])
    for m in range(1, random.randint(3, 5) + 1):
        modulo = Modulo.objects.create(curso=curso, titulo=titulos_modulos[m - 1], ordem=m)
        for a in range(1, random.randint(3, 6) + 1):
            Aula.objects.create(
                modulo=modulo, ordem=a, titulo=f"Aula {a} - {titulos_modulos[m - 1]}",
                tipo=random.choice(tipos_aula), duracao_minutos=random.randint(4, 45),
                video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                previa_gratuita=(m == 1 and a == 1),
            )
    # datas de criação/publicação espalhadas nos últimos meses
    criado = agora - timedelta(days=random.randint(120, 220))
    Curso.objects.filter(pk=curso.pk).update(
        criado_em=criado, publicado_em=criado + timedelta(days=7) if status == "PUBLICADO" else None)
    cursos.append(curso)

# ---------------------------------------------------------------------------
# Cupons
# ---------------------------------------------------------------------------
cupons_dados = [
    ("BEMVINDO10", "10% para novos alunos", "PERCENTUAL", "10", None, None, None, True),
    ("BLACKFRIDAY", "50% na Black Friday", "PERCENTUAL", "50", None, -20, 100, True),
    ("PYTHON30", "R$ 30 nos cursos da Ana", "VALOR_FIXO", "30", "ana.prof", None, 50, True),
    ("DJANGO20", "20% no curso de Django", "PERCENTUAL", "20", "bruno.dev", None, 5, True),
    ("FIGMA15", "15% nos cursos de design", "PERCENTUAL", "15", "carla.design", None, None, False),
    ("NATAL2026", "25% no Natal", "PERCENTUAL", "25", None, 40, None, True),
]
for codigo, descricao, tipo, valor, vend, fim_dias, usos, ativo in cupons_dados:
    inicio = agora - timedelta(days=180) if codigo != "NATAL2026" else agora + timedelta(days=45)
    fim = None
    if fim_dias is not None:
        fim = agora + timedelta(days=fim_dias) if fim_dias > 0 else agora + timedelta(days=fim_dias)
        if codigo == "NATAL2026":
            fim = inicio + timedelta(days=10)
    cupom, criado = Cupom.objects.get_or_create(codigo=codigo, defaults={
        "descricao": descricao, "tipo": tipo, "valor": Decimal(valor),
        "vendedor": vendedores.get(vend), "validade_inicio": inicio, "validade_fim": fim,
        "usos_maximos": usos, "ativo": ativo})
    if criado and codigo == "DJANGO20":
        cupom.cursos.set(Curso.objects.filter(titulo__startswith="Django"))

# ---------------------------------------------------------------------------
# Pedidos, matrículas, progresso e avaliações
# ---------------------------------------------------------------------------
comentarios = {
    5: ["Excelente curso, muito didático!", "Superou minhas expectativas.", "Professor(a) explica muito bem."],
    4: ["Muito bom, recomendo.", "Conteúdo ótimo, poderia ter mais exercícios.", ""],
    3: ["Bom, mas um pouco superficial.", "Esperava mais exemplos práticos.", ""],
    2: ["O áudio de algumas aulas é ruim."],
    1: ["Não gostei, conteúdo desatualizado."],
}

if not Pedido.objects.exists():
    publicados = [c for c in cursos if c.status == "PUBLICADO"]
    cupons_validos = [c for c in Cupom.objects.filter(vendedor__isnull=True) if c.esta_valido()]
    for cliente in clientes:
        for _ in range(random.randint(1, 4)):
            escolhidos = random.sample(publicados, k=random.choice([1, 1, 1, 2, 3]))
            ja_tem = set(Matricula.objects.filter(aluno=cliente).values_list("curso_id", flat=True))
            escolhidos = [c for c in escolhidos if c.pk not in ja_tem]
            if not escolhidos:
                continue
            pedido = Pedido.objects.create(
                cliente=cliente, forma_pagamento=random.choice(["PIX", "PIX", "CARTAO", "BOLETO"]),
                cupom=random.choice(cupons_validos) if random.random() < 0.25 else None)
            for curso in escolhidos:
                ItemPedido.objects.create(pedido=pedido, curso=curso)
            pedido.recalcular_totais()

            data = agora - timedelta(days=random.randint(0, 170), hours=random.randint(0, 23))
            sorteio = random.random()
            if sorteio < 0.75:
                pedido.confirmar_pagamento()
                Pedido.objects.filter(pk=pedido.pk).update(criado_em=data, pago_em=data + timedelta(minutes=15))
            elif sorteio < 0.87:
                Pedido.objects.filter(pk=pedido.pk).update(criado_em=data)  # continua pendente
            elif sorteio < 0.95:
                pedido.cancelar()
                Pedido.objects.filter(pk=pedido.pk).update(criado_em=data)
            else:
                pedido.confirmar_pagamento()
                pedido.cancelar(reembolso=True)
                Pedido.objects.filter(pk=pedido.pk).update(criado_em=data, pago_em=data + timedelta(minutes=15))

    for matricula in Matricula.objects.filter(ativa=True).select_related("curso"):
        aulas = list(Aula.objects.filter(modulo__curso=matricula.curso))
        feitas = random.sample(aulas, k=random.randint(0, len(aulas)))
        ProgressoAula.objects.bulk_create([ProgressoAula(matricula=matricula, aula=a) for a in feitas])
        if aulas and len(feitas) == len(aulas):
            matricula.concluida_em = agora - timedelta(days=random.randint(0, 30))
            matricula.save(update_fields=["concluida_em"])
        if random.random() < 0.6:
            nota = random.choices([5, 4, 3, 2, 1], weights=[45, 30, 15, 6, 4])[0]
            Avaliacao.objects.create(curso=matricula.curso, aluno=matricula.aluno, nota=nota,
                                     comentario=random.choice(comentarios[nota]), aprovada=nota > 1)

print("Banco de dados populado com sucesso!")
print(f"  {User.objects.count()} usuários | {Curso.objects.count()} cursos | {Aula.objects.count()} aulas")
print(f"  {Pedido.objects.count()} pedidos | {Matricula.objects.count()} matrículas | "
      f"{Avaliacao.objects.count()} avaliações | {Cupom.objects.count()} cupons")
print(f"Senha de todos os usuários: {SENHA}  (administrador: admin)")
