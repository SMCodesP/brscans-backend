from django.contrib import admin

from brscans.manhwa.models import Chapter, Manhwa


@admin.register(Manhwa)
class GeeImagemAdmin(admin.ModelAdmin):
    pass


admin.site.register(Chapter)
