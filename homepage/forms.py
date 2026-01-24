from django import forms
from django_recaptcha.fields import ReCaptchaField
from django_recaptcha.widgets import ReCaptchaV2Checkbox

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
    # Das neue Captcha Feld
    captcha = ReCaptchaField(widget=ReCaptchaV2Checkbox(attrs={
        'data-theme': 'light',  # Passt gut zu deinem hellen Design
    }))
