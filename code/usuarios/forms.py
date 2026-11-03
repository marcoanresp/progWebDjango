from django import forms
from django.contrib.auth.models import User

from .models import Perfil


class PerfilForm(forms.ModelForm):
    """Formulário usado pelo próprio usuário para editar seus dados na área logada."""

    first_name = forms.CharField(label="Nome", max_length=150, required=False)
    last_name = forms.CharField(label="Sobrenome", max_length=150, required=False)
    email = forms.EmailField(label="E-mail", required=False)

    class Meta:
        model = Perfil
        fields = ["foto", "bio", "telefone", "data_nascimento", "titulo_profissional", "site", "chave_pix"]
        widgets = {"data_nascimento": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
                   "bio": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        usuario = self.instance.usuario
        self.fields["first_name"].initial = usuario.first_name
        self.fields["last_name"].initial = usuario.last_name
        self.fields["email"].initial = usuario.email
        if not self.instance.eh_vendedor:  # campos exclusivos de vendedores
            for campo in ("titulo_profissional", "site", "chave_pix"):
                self.fields.pop(campo)
        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", "form-control")

    def save(self, commit=True):
        perfil = super().save(commit)
        usuario = perfil.usuario
        usuario.first_name = self.cleaned_data["first_name"]
        usuario.last_name = self.cleaned_data["last_name"]
        usuario.email = self.cleaned_data["email"]
        if commit:
            usuario.save()
        return perfil
