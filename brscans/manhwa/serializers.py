import re
from decimal import Decimal

from django.db.models import Sum
from rest_framework import serializers

from brscans.manhwa.models import (
    Chapter,
    Comment,
    Genre,
    ImageVariants,
    Manhwa,
    Notification,
    Page,
)


class GenreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Genre
        fields = ("id", "name", "slug")


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
            "created_at",
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
        numbers = re.findall(r"\d+", slug or "")
        if not numbers:
            return None

        if len(numbers) >= 2 and re.search(r"-\d+-\d+$", slug or ""):
            return Decimal(f"{numbers[-2]}.{numbers[-1]}")

        return Decimal(numbers[-1])

    def get_ordered_chapters(self, obj):
        chapters = []

        for chapter in Chapter.objects.filter(manhwa=obj.manhwa):
            slug_number = self.get_slug_number(chapter.slug)
            if slug_number is not None:
                chapters.append((slug_number, chapter.id, chapter))

        return sorted(chapters, key=lambda item: (item[0], item[1]))

    def get_next(self, obj):
        current_slug_number = self.get_slug_number(obj.slug)
        if current_slug_number is None:
            return None

        for slug_number, _, chapter in self.get_ordered_chapters(obj):
            if slug_number > current_slug_number:
                return SimpleChapterSerializer(chapter).data

        return None

    def get_previous(self, obj):
        current_slug_number = self.get_slug_number(obj.slug)
        if current_slug_number is None:
            return None

        previous_chapter = None

        for slug_number, _, chapter in self.get_ordered_chapters(obj):
            if slug_number >= current_slug_number:
                break
            previous_chapter = chapter

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
    latest_chapters = serializers.SerializerMethodField()

    def get_latest_chapters(self, obj):
        chapters = obj.chapters.order_by("-id")[:2]
        return SimpleChapterSerializer(chapters, many=True).data

    class Meta:
        model = Manhwa
        fields = (
            "id",
            "is_nsfw",
            "thumbnail",
            "title",
            "original_title",
            "author",
            "status",
            "description",
            "original_description",
            "external_id",
            "slug",
            "hash_external_id",
            "hash_slug",
            "source",
            "identifier",
            "genres",
            "latest_chapters",
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
            "original_title",
            "author",
            "status",
            "description",
            "original_description",
            "external_id",
            "slug",
            "hash_external_id",
            "hash_slug",
            "source",
            "identifier",
            "genres",
            "chapters",
        )


class ManhwaBriefSerializer(serializers.ModelSerializer):
    """Lightweight serializer for embedding manga info inside chapter responses."""

    thumbnail = VariantsSerializer()

    class Meta:
        model = Manhwa
        fields = ("id", "title", "slug", "thumbnail")


class RecentChapterSerializer(serializers.ModelSerializer):
    """Chapter with parent manga info for the recent chapters carousel."""

    manhwa = ManhwaBriefSerializer()

    class Meta:
        model = Chapter
        fields = (
            "id",
            "title",
            "slug",
            "release_date",
            "created_at",
            "manhwa",
        )


class CommentSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True)
    user_avatar = serializers.SerializerMethodField(read_only=True)
    replies = serializers.SerializerMethodField()

    def get_user_avatar(self, obj):
        if hasattr(obj.user, "profile") and obj.user.profile.avatar:
            return obj.user.profile.avatar
        return None

    def get_replies(self, obj):
        # By removing the parent verification, we recursively gather replies indefinitely
        return CommentSerializer(obj.replies.all(), many=True).data

    class Meta:
        model = Comment
        fields = (
            "id",
            "user_name",
            "user_avatar",
            "content",
            "created_at",
            "parent",
            "replies",
            "chapter",
        )


class NotificationSerializer(serializers.ModelSerializer):
    manhwa_title = serializers.CharField(source="manhwa.title", read_only=True)
    manhwa_slug = serializers.CharField(source="manhwa.slug", read_only=True)
    chapter_title = serializers.CharField(
        source="chapter.title", read_only=True
    )
    chapter_slug = serializers.CharField(source="chapter.slug", read_only=True)

    class Meta:
        model = Notification
        fields = (
            "id",
            "type",
            "manhwa",
            "manhwa_title",
            "manhwa_slug",
            "chapter",
            "chapter_title",
            "chapter_slug",
            "read",
            "created_at",
        )
