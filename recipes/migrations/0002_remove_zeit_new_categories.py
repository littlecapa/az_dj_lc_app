from django.db import migrations, models


class Migration(migrations.Migration):
    """
    - zeit-Feld löschen (DROP COLUMN)
    - Drei neue Kategorien: vorspeisen, fisch, kartoffeln
    - notiz bekommt verbose_name='Zubereitung'
    - fleisch umbenannt (Label: 'Fleisch' statt 'Fleisch & Fisch')

    AlterField für choices/verbose_name: nur State-Update (SQL Server
    ändert die DB für Choices nicht → SeparateDatabaseAndState).
    """

    dependencies = [
        ('recipes', '0001_initial'),
    ]

    operations = [
        # 1. zeit-Feld aus der DB entfernen
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "IF EXISTS ("
                        "  SELECT 1 FROM sys.columns "
                        "  WHERE object_id = OBJECT_ID('recipes_rezept') AND name = 'zeit'"
                        ") "
                        "ALTER TABLE recipes_rezept DROP COLUMN zeit;"
                    ),
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[
                migrations.RemoveField(model_name='rezept', name='zeit'),
            ],
        ),

        # 2. Neue Kategorien + verbose_name — nur State, kein SQL
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name='rezept',
                    name='kategorie',
                    field=models.CharField(
                        choices=[
                            ('fruehstueck', 'Frühstück'),
                            ('vorspeisen',  'Vorspeisen'),
                            ('suppen',      'Suppen'),
                            ('vegetarisch', 'Vegetarisch'),
                            ('fleisch',     'Fleisch'),
                            ('fisch',       'Fisch & Meeresfrüchte'),
                            ('kartoffeln',  'Kartoffeln'),
                            ('pasta',       'Pasta & Reis'),
                            ('backen',      'Backen'),
                            ('dessert',     'Desserts'),
                            ('snacks',      'Snacks & Dips'),
                            ('getraenke',   'Getränke'),
                        ],
                        default='vegetarisch',
                        max_length=50,
                    ),
                ),
                migrations.AlterField(
                    model_name='rezept',
                    name='notiz',
                    field=models.TextField(blank=True, verbose_name='Zubereitung'),
                ),
            ],
        ),
    ]
