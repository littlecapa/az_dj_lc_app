from django import forms


TRAVEL_CLASS_CHOICES = [
    ('1', 'Economy'),
    ('2', 'Premium Economy'),
    ('3', 'Business'),
    ('4', 'First Class'),
]

class FlightSearchForm(forms.Form):
    departure_airport = forms.CharField(
        label='Startflughafen',
        max_length=3,
        widget=forms.TextInput(attrs={
            'class': 'form-control text-uppercase',
            'placeholder': 'z.B. FRA',
            'maxlength': '3',
            'style': 'text-transform: uppercase;',
        }),
    )
    arrival_airport = forms.CharField(
        label='Zielflughafen',
        max_length=3,
        widget=forms.TextInput(attrs={
            'class': 'form-control text-uppercase',
            'placeholder': 'z.B. BKK',
            'maxlength': '3',
            'style': 'text-transform: uppercase;',
        }),
    )
    travel_class = forms.ChoiceField(
        label='Klasse',
        choices=TRAVEL_CLASS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    adults = forms.IntegerField(
        label='Erwachsene',
        min_value=1,
        max_value=9,
        initial=1,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
    )
    direct_only = forms.BooleanField(
        label='Nur Direktflüge',
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )
    outbound_date = forms.DateField(
        label='Hinflug',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    return_date = forms.DateField(
        label='Rückflug (leer = Einweg)',
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    def clean_departure_airport(self):
        return self.cleaned_data['departure_airport'].upper()

    def clean_arrival_airport(self):
        return self.cleaned_data['arrival_airport'].upper()

    def clean(self):
        cleaned = super().clean()
        outbound = cleaned.get('outbound_date')
        ret = cleaned.get('return_date')
        if ret and outbound and ret < outbound:
            self.add_error('return_date', 'Rückflugdatum muss nach dem Hinflugdatum liegen.')
        return cleaned


_AIRPORT_WIDGET = {
    'class': 'form-control text-uppercase',
    'maxlength': '3',
    'style': 'text-transform: uppercase;',
}


class RouteSearchForm(forms.Form):
    departure_airport = forms.CharField(
        label='Startflughafen',
        max_length=3,
        widget=forms.TextInput(attrs={**_AIRPORT_WIDGET, 'placeholder': 'z.B. FRA'}),
    )
    arrival_airport = forms.CharField(
        label='Zielflughafen',
        max_length=3,
        widget=forms.TextInput(attrs={**_AIRPORT_WIDGET, 'placeholder': 'z.B. BKK'}),
    )
    direct_only = forms.BooleanField(
        label='Nur Direktverbindungen',
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )
    show_live = forms.BooleanField(
        label='Heutige Flüge anzeigen (Aviationstack)',
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    def clean_departure_airport(self):
        return self.cleaned_data['departure_airport'].upper()

    def clean_arrival_airport(self):
        return self.cleaned_data['arrival_airport'].upper()
