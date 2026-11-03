"""
Remove os dados de cursos, vendas e usuários não administradores.

Execute:
    python3 scripts-bd/limpa_bd.py
"""
import os
import sys

import django

# Caminho base do projeto (um nível acima da pasta scripts-bd)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portal_cursos.settings")
django.setup()

from django.contrib.auth.models import User  # noqa: E402

from cursos.models import Categoria, Curso, Matricula, Tag  # noqa: E402
from vendas.models import Cupom, Pedido  # noqa: E402

Matricula.objects.all().delete()
Pedido.objects.all().delete()
Cupom.objects.all().delete()
Curso.objects.all().delete()
Categoria.objects.all().delete()
Tag.objects.all().delete()
User.objects.filter(is_superuser=False).delete()

print("Dados removidos com sucesso!")
