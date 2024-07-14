from rest_framework import serializers

from brscans.manhwa.models import Chapter, ImageVariants, Manhwa, Page


class VariantsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImageVariants
        fields = "__all__"


class PageSerializer(serializers.ModelSerializer):
    images = VariantsSerializer()

    class Meta:
        model = Page
        fields = "__all__"


class ChapterSerializer(serializers.ModelSerializer):
    pages = PageSerializer(many=True)

    class Meta:
        model = Chapter
        fields = ("id", "title", "slug", "release_date", "pages")


class ManhwaSerializer(serializers.ModelSerializer):
    thumbnail = VariantsSerializer()
    chapters = ChapterSerializer(many=True)

    class Meta:
        model = Manhwa
        fields = (
            "id",
            "thumbnail",
            "title",
            "author",
            "status",
            "description",
            "external_id",
            "slug",
            "hash_external_id",
            "hash_slug",
            "source",
            "identifier",
            "genres",
            "chapters",
        )
