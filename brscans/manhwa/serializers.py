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


class SimpleChapterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chapter
        fields = ("id", "title", "slug", "release_date")


class ChapterSerializer(serializers.ModelSerializer):
    pages = PageSerializer(many=True)

    class Meta:
        model = Chapter
        fields = ("id", "title", "slug", "release_date", "pages")


class ChapterNextPreviousSerializer(serializers.ModelSerializer):
    next = serializers.SerializerMethodField()
    previous = serializers.SerializerMethodField()
    pages = PageSerializer(many=True)

    def get_next(self, obj):
        next_chapter = (
            Chapter.objects.filter(manhwa=obj.manhwa, id__gt=obj.id)
            .order_by("id")
            .first()
        )
        if next_chapter:
            return SimpleChapterSerializer(next_chapter).data
        return None

    def get_previous(self, obj):
        previous_chapter = (
            Chapter.objects.filter(manhwa=obj.manhwa, id__lt=obj.id)
            .order_by("-id")
            .first()
        )
        if previous_chapter:
            return SimpleChapterSerializer(previous_chapter).data
        return None

    class Meta:
        model = Chapter
        fields = ("id", "title", "slug", "release_date", "pages", "next", "previous")


class ManhwaSerializer(serializers.ModelSerializer):
    thumbnail = VariantsSerializer()

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
        )


class ManhwaDetailSerializer(serializers.ModelSerializer):
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
