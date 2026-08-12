"""
Migration 0028: price_fetch_blocked auf Asset.

Wenn ein Kurs-Abruf für ein Asset fehlschlägt, wird dieses Flag gesetzt
(+ ein Jira-Bug-Ticket angelegt). Solange es True ist, wird kein weiterer
automatischer Abruf versucht — verhindert Ticket-Duplikate. Manuell nach
Bearbeitung des Tickets wieder auf False setzen.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0027_fiftytwoweekrange_skip_yahoo_nullable'),
    ]

    operations = [
        migrations.AddField(
            model_name='asset',
            name='price_fetch_blocked',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'True = kein automatischer Kurs-Abruf mehr (es existiert bereits ein '
                    'offenes Jira-Bug-Ticket dazu). Nach Bearbeitung des Tickets manuell '
                    'wieder auf False setzen.'
                ),
            ),
        ),
    ]
