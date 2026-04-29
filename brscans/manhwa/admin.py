from django.contrib import admin

from brscans.manhwa.models import Chapter, ImageVariants, Manhwa

# admin.site.register(Manhwa)
admin.site.register(ImageVariants)


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ("title", "manhwa", "release_date")
    list_select_related = ("manhwa",)
    search_fields = ("title", "identifier")
    raw_id_fields = ("manhwa",)


@admin.register(Manhwa)
class ManhwaAdmin(admin.ModelAdmin):
    list_display = ("title", "source", "thumbnail")
    list_select_related = ("thumbnail",)
    list_filter = ("source",)
    search_fields = ("title",)
    raw_id_fields = ("thumbnail",)
    filter_horizontal = ("genres",)


# # 2790 49716
