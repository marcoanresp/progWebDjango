from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth import login as login_django
from django.contrib.auth import logout as logout_django
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import PerfilForm
from .models import Perfil


def login(request):
    if request.method == "GET":
        return render(request, 'login.html')
    else:
        usuario = request.POST.get('usuario')
        senha = request.POST.get('senha')
        user = authenticate(username=usuario, password=senha)
        if user:
            login_django(request, user)
            proxima = request.GET.get('next', '')
            if url_has_allowed_host_and_scheme(proxima, allowed_hosts={request.get_host()}):
                return redirect(proxima)
            return redirect('principal')
        else:
            messages.error(request, 'Usuário ou senha inválidos. Tente novamente.')
            return render(request, 'login.html')


def cadastro(request):
    if request.method == "GET":
        return render(request, 'cadastro.html', {'tipos': Perfil.Tipo.choices})
    else:  # senão será via método "POST"
        usuario = request.POST.get('usuario', '').strip()
        nome = request.POST.get('nome', '').strip()
        email = request.POST.get('email', '').strip()
        senha = request.POST.get('senha', '')
        confirmacao = request.POST.get('confirmacao', '')
        tipo = request.POST.get('tipo', Perfil.Tipo.CLIENTE)
        contexto = {'tipos': Perfil.Tipo.choices}

        if tipo not in Perfil.Tipo.values:
            tipo = Perfil.Tipo.CLIENTE
        if not usuario or not senha:
            messages.error(request, 'Informe o usuário e a senha.')
            return render(request, 'cadastro.html', contexto)
        if senha != confirmacao:
            messages.error(request, 'As senhas não conferem.')
            return render(request, 'cadastro.html', contexto)
        # Verifica se o usuário já está cadastrado
        if User.objects.filter(username=usuario).exists():
            messages.error(request, 'Já existe um usuário com esse nome. Tente novamente.')
            return render(request, 'cadastro.html', contexto)
        try:
            validate_password(senha)
        except ValidationError as erro:
            for mensagem in erro.messages:
                messages.error(request, mensagem)
            return render(request, 'cadastro.html', contexto)

        # Cria e salva o usuário. O sinal post_save cria o perfil automaticamente.
        partes = nome.split(' ', 1)
        user = User.objects.create_user(username=usuario, email=email, password=senha,
                                        first_name=partes[0], last_name=partes[1] if len(partes) > 1 else '')
        perfil = user.perfil
        perfil.tipo = tipo
        perfil.save()  # o sinal coloca o usuário no grupo correto (Clientes ou Vendedores)

        login_django(request, user)
        messages.success(request, 'Cadastro realizado com sucesso! Bem-vindo(a) ao EduMarket.')
        if perfil.eh_vendedor:
            return redirect('painel_vendedor')
        return redirect('principal')


def logout(request):
    logout_django(request)
    messages.info(request, 'Você saiu da sua conta.')
    return redirect('login')


@login_required
def perfil(request):
    perfil_usuario, _ = Perfil.objects.get_or_create(usuario=request.user)
    if request.method == "POST":
        form = PerfilForm(request.POST, request.FILES, instance=perfil_usuario)
        if form.is_valid():
            form.save()
            messages.success(request, 'Perfil atualizado com sucesso!')
            return redirect('perfil')
    else:
        form = PerfilForm(instance=perfil_usuario)
    return render(request, 'perfil.html', {'form': form})
