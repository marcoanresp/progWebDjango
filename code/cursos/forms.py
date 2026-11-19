from django import forms

from .models import Avaliacao


class AvaliacaoForm(forms.ModelForm):
    """
    Formulário usado pelo aluno para avaliar um curso no site.
    O curso e o aluno não aparecem no formulário: a view preenche os dois
    (o aluno é sempre o usuário logado, assim ninguém avalia em nome de outra pessoa).
    """

    NOTAS = [(5, "Excelente"), (4, "Muito bom"), (3, "Bom"), (2, "Ruim"), (1, "Péssimo")]

    nota = forms.TypedChoiceField(choices=NOTAS, coerce=int, widget=forms.RadioSelect,
                                  error_messages={"required": "Escolha uma nota de 1 a 5 estrelas."})
    comentario = forms.CharField(label="Comentário", required=False, max_length=1000,
                                 widget=forms.Textarea(attrs={
                                     "rows": 4, "class": "form-control",
                                     "placeholder": "Conte o que achou do curso (opcional)"}))

    class Meta:
        model = Avaliacao
        fields = ["nota", "comentario"]
