from hashlib import sha256

from django.db.models import Q
from django.utils.datetime_safe import datetime
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from slugify import slugify

from brscans.manhwa.models import Chapter
from brscans.manhwa.serializers import ChapterNextPreviousSerializer, ChapterSerializer
from brscans.manhwa.tasks.images_variants import (
    merge_pages_original,
    process_image_translate,
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

    @action(detail=True, methods=["get"])
    def fix(self, request, pk):
        chapter = Chapter.objects.get(pk=pk)
        pages = chapter.pages.filter(
            Q(images__isnull=True)
            | Q(images__translated__isnull=True)
            | Q(images__original__isnull=True)
            | Q(images__original="")
            | Q(images__translated="")
        )

        for page in pages:
            variants = page.images
            process_image_translate(
                variants.pk,
                variants.original.url,
                [
                    "chapters",
                    str(chapter.pk),
                ],
                chapter.manhwa.pk,
            )

        return Response({"status": "ok"})

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
