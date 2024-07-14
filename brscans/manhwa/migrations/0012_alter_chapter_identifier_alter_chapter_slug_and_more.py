# Generated by Django 4.2.9 on 2024-07-11 03:11

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("manhwa", "0011_chapter_identifier"),
    ]

    operations = [
        migrations.AlterField(
            model_name="chapter",
            name="identifier",
            field=models.CharField(max_length=255, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name="chapter",
            name="slug",
            field=models.SlugField(max_length=255),
        ),
        migrations.AlterField(
            model_name="chapter",
            name="title",
            field=models.CharField(max_length=255),
        ),
    ]
