# Generated for telegram_app

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='TelegramMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('message', models.TextField(verbose_name='Nachricht')),
                ('trigger', models.CharField(blank=True, default='', help_text='Für zukünftige automatische Auslöser (z.B. Event-Name). Aktuell ungenutzt.', max_length=64, verbose_name='Trigger')),
                ('sent_at', models.DateTimeField(auto_now_add=True, verbose_name='Gesendet am')),
            ],
            options={
                'verbose_name': 'Telegram-Nachricht',
                'verbose_name_plural': 'Telegram-Nachrichten',
                'ordering': ['-sent_at'],
            },
        ),
    ]
