from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("manhwa", "0034_chapter_discord_notified"),
    ]

    operations = [
        # Só o choice novo: o admin passa a distinguir fonte fora do ar de
        # captcha. Nenhuma coluna muda.
        migrations.AlterField(
            model_name="manhwa",
            name="source_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("ok", "OK"),
                    ("redirected", "Domínio mudou (redireciona)"),
                    ("not_found", "Não encontrado (404)"),
                    ("dead", "Domínio morto (DNS/TLS)"),
                    ("offline", "Fora do ar (403/503 sem challenge)"),
                    ("blocked", "Bloqueado (captcha/403/429)"),
                    ("http_error", "Erro HTTP"),
                    ("timeout", "Timeout"),
                    ("parser_error", "Parser quebrado"),
                    ("no_url", "Sem URL"),
                ],
                max_length=32,
                null=True,
            ),
        ),
    ]
