from django.contrib import admin

from brscans.manhwa.models import Manhwa


@admin.register(Manhwa)
class GeeImagemAdmin(admin.ModelAdmin):
    pass
