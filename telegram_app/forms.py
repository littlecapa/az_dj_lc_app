from django import forms


class TelegramMessageForm(forms.Form):
    message = forms.CharField(
        label='Nachricht',
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 6,
            'placeholder': 'Nachricht an Telegram...'
        })
    )
