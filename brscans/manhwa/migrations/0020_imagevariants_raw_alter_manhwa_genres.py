# Generated by Django 4.2.9 on 2025-05-18 17:36

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("manhwa", "0019_manhwa_is_nsfw"),
    ]

    operations = [
        migrations.AddField(
            model_name="imagevariants",
            name="raw",
            field=models.ImageField(null=True, upload_to=""),
        ),
        migrations.AlterField(
            model_name="manhwa",
            name="genres",
            field=models.ManyToManyField(
                blank=True, related_name="manhwas", to="manhwa.genre"
            ),
        ),
    ]
