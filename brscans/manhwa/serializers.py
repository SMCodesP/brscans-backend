from django.db.models import Sum
from django.db.models.expressions import RawSQL
from rest_framework import serializers

from brscans.manhwa.models import Chapter, ImageVariants, Manhwa, Page


class VariantsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImageVariants
        fields = "__all__"


class VariantsUpdateSerializer(serializers.ModelSerializer):
    translated = serializers.CharField(required=False, max_length=255)
    raw = serializers.CharField(required=False, max_length=255)

    class Meta:
        model = ImageVariants
        fields = "__all__"


class PageSerializer(serializers.ModelSerializer):
    images = VariantsSerializer()

    class Meta:
        model = Page
        fields = "__all__"


class SimpleChapterSerializer(serializers.ModelSerializer):
    quantity_merged = serializers.SerializerMethodField()

    def get_quantity_merged(self, obj):
        return obj.pages.aggregate(total=Sum("quantity_merged"))["total"]

    class Meta:
        model = Chapter
        fields = (
            "id",
            "title",
            "slug",
            "release_date",
            "quantity_pages",
            "quantity_merged",
        )


class ChapterSerializer(serializers.ModelSerializer):
    pages = PageSerializer(many=True)
    quantity_merged = serializers.SerializerMethodField()

    def get_quantity_merged(self, obj):
        return obj.pages.aggregate(total=Sum("quantity_merged"))["total"]

    class Meta:
        model = Chapter
        fields = (
            "id",
            "title",
            "slug",
            "release_date",
            "quantity_pages",
            "quantity_merged",
            "pages",
        )


class ChapterNextPreviousSerializer(serializers.ModelSerializer):
    next = serializers.SerializerMethodField()
    previous = serializers.SerializerMethodField()
    pages = PageSerializer(many=True)
    quantity_merged = serializers.SerializerMethodField()

    def get_quantity_merged(self, obj):
        return obj.pages.aggregate(total=Sum("quantity_merged"))["total"]

    def get_slug_number(self, slug):
        """Extrai o primeiro número do slug como inteiro."""
        import re

        match = re.search(r"\d+", slug)
        if match:
            return int(match.group())
        return None

    def get_next(self, obj):
        # Calcula o slug_number do capítulo atual
        current_slug_number = self.get_slug_number(obj.slug)
        if current_slug_number is None:
            return None

        # Busca o próximo capítulo com slug_number maior que o atual
        next_chapter = (
            Chapter.objects.filter(manhwa=obj.manhwa)
            .annotate(
                slug_number=RawSQL(
                    """
                    CASE 
                        WHEN slug ~ '[0-9]+' 
                        THEN CAST(
                            (SELECT REGEXP_MATCHES(slug, '[0-9]+'))[1] 
                            AS INTEGER
                        ) 
                        ELSE NULL 
                    END
                    """,
                    [],
                )
            )
            .filter(slug_number__gt=current_slug_number)
            .order_by("slug_number")
            .first()
        )
        if next_chapter:
            return SimpleChapterSerializer(next_chapter).data
        return None

    def get_previous(self, obj):
        previous_chapter = (
            Chapter.objects.filter(manhwa=obj.manhwa, id__lt=obj.id)
            .annotate(
                slug_number=RawSQL(
                    """
                    CASE 
                        WHEN slug ~ '[0-9]+' 
                        THEN CAST(
                            (SELECT REGEXP_MATCHES(slug, '[0-9]+'))[1] 
                            AS INTEGER
                        ) 
                        ELSE NULL 
                    END
                    """,
                    [],
                )
            )
            .order_by("-slug_number")
            .first()
        )
        if previous_chapter:
            return SimpleChapterSerializer(previous_chapter).data
        return None

    class Meta:
        model = Chapter
        fields = (
            "id",
            "title",
            "slug",
            "release_date",
            "quantity_pages",
            "quantity_merged",
            "pages",
            "next",
            "previous",
        )


class ManhwaSerializer(serializers.ModelSerializer):
    thumbnail = VariantsSerializer()

    class Meta:
        model = Manhwa
        fields = (
            "id",
            "is_nsfw",
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
    chapters = SimpleChapterSerializer(many=True)

    class Meta:
        model = Manhwa
        fields = (
            "id",
            "is_nsfw",
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
