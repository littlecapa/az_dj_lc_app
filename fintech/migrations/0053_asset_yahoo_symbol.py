from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fintech", "0052_currencyclass_add_krw_cny_hkd_mxn_pln_zar_twd"),
    ]

    operations = [
        migrations.AddField(
            model_name="asset",
            name="yahoo_symbol",
            field=models.CharField(
                max_length=20,
                null=True,
                blank=True,
                help_text=(
                    "Manueller Yahoo-Finance-Ticker (z.B. 'AAL.L'), falls Yahoos ISIN-Suche "
                    "für dieses Asset nichts findet (isin2price schlägt sonst fehl). Nur "
                    "setzen, wenn nötig — sonst wird die ISIN-Suche normal verwendet. "
                    "Achtung: anderes Format als 'symbol' (TradingView)."
                ),
            ),
        ),
    ]
