from django import forms

class ContactForm(forms.Form):
    name = forms.CharField(
        label='Name',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control border-light shadow-sm py-3', # border-light macht den Rahmen dünn/hell
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
