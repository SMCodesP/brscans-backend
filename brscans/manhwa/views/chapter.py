from hashlib import sha256

from django.utils.datetime_safe import datetime
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from slugify import slugify

from brscans.manhwa.models import Chapter, ReadChapter
from brscans.manhwa.serializers import (
    ChapterNextPreviousSerializer,
    ChapterSerializer,
    with_quantity_merged,
)
from brscans.manhwa.tasks.images_variants import merge_pages_original
from brscans.manhwa.tasks.panel import panel_fix_chapter
from brscans.pagination import TotalPagination
from brscans.wrapper.sources.Generic import Generic


class ChapterViewSet(viewsets.ModelViewSet):
    serializer_class = ChapterSerializer
    queryset = (
        with_quantity_merged(Chapter.objects.all())
        .prefetch_related("pages", "pages__images")
        .select_related("manhwa")
    )
    pagination_class = TotalPagination

    def retrieve(self, request, *args, **kwargs):
        self.serializer_class = ChapterNextPreviousSerializer
        return super().retrieve(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def fix(self, request, pk):
        """Mesma entrada do botão do painel, agora fora da requisição: reparar
        dentro da API estoura o Gateway e repete o trabalho a cada clique."""
        chapter = Chapter.objects.get(pk=pk)
        panel_fix_chapter(chapter.pk)
        return Response({"status": "queued"}, status=202)

    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, pk=None):
        if not request.user.is_authenticated:
            return Response({"error": "Autenticação necessária."}, status=401)

        chapter = self.get_object()
        ReadChapter.objects.get_or_create(
            user=request.user, manhwa=chapter.manhwa, chapter=chapter
        )
        return Response({"status": "Marcado como lido."})

    @action(detail=False, methods=["get"])
    def download(self, request):
        link = request.query_params.get("link")
        identifier = sha256(link.encode("utf-8")).hexdigest()

        chapter = (
            with_quantity_merged(Chapter.objects.all())
            .prefetch_related("pages", "pages__images")
            .filter(identifier=identifier)
            .first()
        )

        if chapter:
            serializer = ChapterSerializer(chapter)
            return Response(serializer.data)

        chapter = Chapter.objects.create(
            release_date=datetime.now(),
            identifier=identifier,
            source=link,
        )

        result = Generic.chapter(chapter)
        chapter.title = result["title"]
        chapter.slug = slugify(result["title"])
        chapter.save()

        merge_pages_original(
            result["pages"], chapter.pk, ["chapters", str(chapter.pk)]
        )

        serializer = ChapterSerializer(chapter)
        return Response(serializer.data)
