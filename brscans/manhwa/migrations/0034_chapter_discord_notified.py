from django.db import migrations, models


def mark_existing(apps, schema_editor):
    # Só capítulos criados daqui em diante são novidade para o Discord.
    apps.get_model("manhwa", "Chapter").objects.update(discord_notified=True)


class Migration(migrations.Migration):
    dependencies = [("manhwa", "0033_page_work_fields")]

    operations = [
        migrations.AddField(
            model_name="chapter",
            name="discord_notified",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(mark_existing, migrations.RunPython.noop),
    ]
