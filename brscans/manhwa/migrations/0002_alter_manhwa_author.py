# Generated by Django 5.0.1 on 2024-04-06 21:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('manhwa', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='manhwa',
            name='author',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
