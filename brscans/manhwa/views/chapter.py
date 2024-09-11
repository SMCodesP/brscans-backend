from hashlib import sha256
from django.utils.datetime_safe import datetime
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from slugify import slugify

from brscans.manhwa.models import Chapter
from brscans.manhwa.serializers import ChapterNextPreviousSerializer, ChapterSerializer
from brscans.manhwa.tasks.images_variants import (
    merge_pages_original,
)
from brscans.pagination import TotalPagination
from brscans.wrapper.sources.Generic import Generic


class ChapterViewSet(viewsets.ModelViewSet):
    serializer_class = ChapterSerializer
    queryset = Chapter.objects.all().prefetch_related("pages", "pages__images")
    pagination_class = TotalPagination

    def retrieve(self, request, *args, **kwargs):
        self.serializer_class = ChapterNextPreviousSerializer
        return super().retrieve(request, *args, **kwargs)

    @action(detail=False, methods=["get"])
    def download(self, request):
        link = request.query_params.get("link")
        identifier = sha256(link.encode("utf-8")).hexdigest()

        chapter = (
            Chapter.objects.filter(identifier=identifier)
            .prefetch_related("pages", "pages__images")
            .first()
        )

        if chapter:
            serializer = ChapterSerializer(chapter)
            return Response(serializer.data)

        result = Generic.chapter(link)

        chapter = Chapter.objects.create(
            title=result["title"],
            slug=slugify(result["title"]),
            release_date=datetime.now(),
            identifier=identifier,
        )

        merge_pages_original(result["pages"], chapter.pk, ["chapters", str(chapter.pk)])

        serializer = ChapterSerializer(chapter)
        return Response(serializer.data)
