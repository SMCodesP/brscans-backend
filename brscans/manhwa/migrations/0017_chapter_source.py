# Generated by Django 4.2.9 on 2024-07-11 22:56

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("manhwa", "0016_delete_source_alter_manhwa_source"),
    ]

    operations = [
        migrations.AddField(
            model_name="chapter",
            name="source",
            field=models.URLField(blank=True, null=True),
        ),
    ]
