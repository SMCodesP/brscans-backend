from django.db.models.expressions import RawSQL
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from brscans.manhwa.models import Chapter
from brscans.manhwa.serializers import ChapterSerializer, SimpleChapterSerializer
from brscans.manhwa.tasks.sync_chapter import fix_pages
from brscans.manhwa.tasks.upscale import upscale_pages
from brscans.wrapper.sources import get_source_by_link
from brscans.wrapper.sources.Generic import Generic


class ManhwaChapterViewSet(viewsets.ModelViewSet):
    serializer_class = ChapterSerializer
    queryset = Chapter.objects.all()

    def get_queryset(self):
        return (
            Chapter.objects.filter(manhwa=self.kwargs["manhwa_pk"])
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
            .order_by("slug_number")
        )

    def list(self, request, *args, **kwargs):
        self.serializer_class = SimpleChapterSerializer
        return super().list(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def fix(self, request, manhwa_pk=None, pk=None):
        chapter = Chapter.objects.get(manhwa=manhwa_pk, pk=pk)

        fix_pages(chapter.pk)
        return Response({"status": "fixed"})

    @action(detail=True, methods=["get"])
    def teste(self, request, manhwa_pk=None, pk=None):
        chapter = Chapter.objects.get(manhwa=manhwa_pk, pk=pk)

        Source: Generic = get_source_by_link(chapter.source)
        chapter = Source.chapter(chapter.source)
        return Response(chapter)

    @action(detail=True, methods=["get"])
    def upscale(self, request, manhwa_pk=None, pk=None):
        chapter = Chapter.objects.get(manhwa=manhwa_pk, pk=pk)
        upscale_pages(chapter.pk)
        return Response({"status": "upscaled"})