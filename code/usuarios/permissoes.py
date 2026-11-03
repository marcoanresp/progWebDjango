"""
Definição dos grupos de usuários e de suas permissões.

- Vendedores: acessam o ambiente administrativo, mas só enxergam/alteram os
  próprios cursos, módulos, aulas, cupons e vendas (ver mixins em cursos/admin.py).
- Clientes: não acessam o ambiente administrativo. Usam apenas a área do
  aluno no site (meus cursos, avaliações, pedidos).
- Superusuário (administrador da plataforma): acesso total.
"""
from django.contrib.auth.models import Group, Permission

GRUPO_VENDEDORES = "Vendedores"
GRUPO_CLIENTES = "Clientes"

PERMISSOES = {
    GRUPO_VENDEDORES: [
        # cursos
        "cursos.add_curso", "cursos.change_curso", "cursos.delete_curso", "cursos.view_curso",
        "cursos.add_modulo", "cursos.change_modulo", "cursos.delete_modulo", "cursos.view_modulo",
        "cursos.add_aula", "cursos.change_aula", "cursos.delete_aula", "cursos.view_aula",
        "cursos.view_categoria",
        "cursos.add_tag", "cursos.view_tag",
        "cursos.view_matricula",
        "cursos.view_avaliacao",
        # vendas
        "vendas.add_cupom", "vendas.change_cupom", "vendas.delete_cupom", "vendas.view_cupom",
        "vendas.view_pedido",
        # usuarios
        "usuarios.view_perfil", "usuarios.change_perfil",
    ],
    GRUPO_CLIENTES: [
        "cursos.view_curso",
        "cursos.view_matricula",
        "cursos.add_avaliacao", "cursos.change_avaliacao", "cursos.view_avaliacao",
        "vendas.add_pedido", "vendas.view_pedido",
    ],
}


def configurar_grupos():
    """Cria (ou atualiza) os grupos e associa as permissões definidas acima."""
    resultado = {}
    for nome_grupo, codigos in PERMISSOES.items():
        grupo, _ = Group.objects.get_or_create(name=nome_grupo)
        permissoes = []
        for codigo in codigos:
            app_label, codename = codigo.split(".")
            perm = Permission.objects.filter(content_type__app_label=app_label, codename=codename).first()
            if perm:
                permissoes.append(perm)
        grupo.permissions.set(permissoes)
        resultado[nome_grupo] = len(permissoes)
    return resultado


def sincronizar_usuario(perfil):
    """Coloca o usuário no grupo correspondente ao tipo do perfil e ajusta o acesso ao admin."""
    usuario = perfil.usuario
    vendedores, _ = Group.objects.get_or_create(name=GRUPO_VENDEDORES)
    clientes, _ = Group.objects.get_or_create(name=GRUPO_CLIENTES)
    if perfil.eh_vendedor:
        usuario.groups.add(vendedores)
        usuario.groups.remove(clientes)
        is_staff = True
    else:
        usuario.groups.add(clientes)
        usuario.groups.remove(vendedores)
        is_staff = usuario.is_superuser
    if usuario.is_staff != is_staff:
        usuario.is_staff = is_staff
        usuario.save(update_fields=["is_staff"])
