from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('homepage', '0009_blogpost_slug_not_unique'),
    ]

    operations = [
        migrations.CreateModel(
            name='ChessPosition',
            fields=[
                ('fen', models.CharField(
                    max_length=90, primary_key=True, serialize=False,
                    help_text="FEN-Figurenplatzierung, z. B. 'kbK5/pp6/1P6/8/8/8/8/R7'",
                )),
                ('valid_moves_regex', models.CharField(
                    max_length=200,
                    help_text="Regulärer Ausdruck (re.fullmatch, case-insensitive), z. B. '^[RT]a6$'",
                )),
            ],
            options={
                'verbose_name': 'Chess Captcha Position',
                'verbose_name_plural': 'Chess Captcha Positions',
            },
        ),
    ]
