# Generated by Django 5.0.4 on 2024-04-07 16:40

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('manhwa', '0002_alter_manhwa_author'),
    ]

    operations = [
        migrations.CreateModel(
            name='ImageVariants',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('identifier', models.CharField(max_length=40, unique=True)),
                ('minimum', models.ImageField(null=True, upload_to='')),
                ('medium', models.ImageField(null=True, upload_to='')),
                ('large', models.ImageField(null=True, upload_to='')),
                ('original', models.ImageField(null=True, upload_to='')),
            ],
        ),
        migrations.AddField(
            model_name='manhwa',
            name='thumbnail',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='manhwa.imagevariants'),
        ),
    ]
