from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fintech", "0045_nu_holdings_manual_holding"),
    ]

    operations = [
        migrations.AddField(
            model_name="asset",
            name="price_fetch_failing_since",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text=(
                    "Zeitpunkt des ersten fehlgeschlagenen Kurs-Abrufs in Folge. Wird bei "
                    "jedem erfolgreichen Abruf zurückgesetzt. Erst wenn seit diesem "
                    "Zeitpunkt mehr als 24h vergangen sind, wird price_fetch_blocked "
                    "gesetzt und ein Jira-Ticket angelegt (statt bei jedem einzelnen "
                    "Fehlschlag)."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="asset",
            name="price_fetch_blocked",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "True = kein automatischer Kurs-Abruf mehr (es existiert bereits ein "
                    "offenes Jira-Bug-Ticket dazu, da der Abruf seit über 24h fehlschlägt). "
                    "Nach Bearbeitung des Tickets manuell wieder auf False setzen."
                ),
            ),
        ),
    ]
