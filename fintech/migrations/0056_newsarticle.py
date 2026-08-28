import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fintech", "0055_unblock_fin_442_assets"),
    ]

    operations = [
        migrations.CreateModel(
            name="NewsArticle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("company_name", models.CharField(help_text="Denormalisiert, auch wenn asset gesetzt ist.", max_length=200)),
                ("title", models.CharField(max_length=500)),
                ("link", models.URLField(max_length=2048, unique=True)),
                ("source", models.CharField(blank=True, max_length=100)),
                ("provider", models.CharField(choices=[("yahoo", "Yahoo Finance"), ("google_news", "Google News")], max_length=20)),
                ("thumbnail_url", models.URLField(blank=True, max_length=2048, null=True)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("fetched_at", models.DateTimeField(auto_now_add=True)),
                ("asset", models.ForeignKey(
                    to='fintech.asset', on_delete=django.db.models.deletion.CASCADE,
                    null=True, blank=True, related_name='news_articles',
                    help_text="NULL bei manuell erfassten Fonds-Positionen ohne Asset-Match (siehe company_name).",
                )),
            ],
            options={
                "verbose_name": "News-Artikel",
                "verbose_name_plural": "News-Artikel",
                "ordering": ["-published_at", "-fetched_at"],
            },
        ),
        migrations.AddIndex(
            model_name="newsarticle",
            index=models.Index(fields=["-published_at"], name="fintech_new_publish_idx"),
        ),
    ]
