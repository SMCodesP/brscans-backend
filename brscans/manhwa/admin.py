from django.contrib import admin

from brscans.manhwa.models import Chapter, ImageVariants, Manhwa


@admin.register(Manhwa)
class GeeImagemAdmin(admin.ModelAdmin):
    pass


admin.site.register(Chapter)
admin.site.register(ImageVariants)

# # 2790 49716
