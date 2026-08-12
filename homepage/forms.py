from django import forms

from .chess_captcha import is_captcha_answer_correct


class ContactForm(forms.Form):
    name = forms.CharField(
        label='Name',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control border-light shadow-sm py-3',
            'placeholder': 'Name'
        })
    )
    email = forms.EmailField(
        label='E-Mail*',
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control border-light shadow-sm py-3',
            'placeholder': 'E-Mail*'
        })
    )
    message = forms.CharField(
        label='Message',
        widget=forms.Textarea(attrs={
            'class': 'form-control border-light shadow-sm',
            'rows': 6,
            'placeholder': 'Message'
        }),
        required=False
    )
    captcha_answer = forms.CharField(
        label='Captcha',
        required=True,
        max_length=3,
        widget=forms.TextInput(attrs={
            'class': 'form-control border-light shadow-sm py-3',
            'placeholder': 'z.B. Ra6',
            'maxlength': '3',
            'autocomplete': 'off',
        })
    )

    def clean_captcha_answer(self):
        answer = self.cleaned_data.get('captcha_answer', '')
        if not is_captcha_answer_correct(answer):
            raise forms.ValidationError("Falsche Antwort — bitte den besten Zug für Weiß angeben.")
        return answer