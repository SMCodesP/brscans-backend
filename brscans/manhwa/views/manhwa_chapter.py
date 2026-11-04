from django.db.models.expressions import RawSQL
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from brscans.manhwa.models import Chapter
from brscans.manhwa.serializers import (
    ChapterSerializer,
    SimpleChapterSerializer,
    with_quantity_merged,
)
from brscans.manhwa.tasks.sync_chapter import fix_pages


class ManhwaChapterViewSet(viewsets.ModelViewSet):
    serializer_class = ChapterSerializer
    queryset = Chapter.objects.all()

    def get_queryset(self):
        return (
            with_quantity_merged(
                Chapter.objects.filter(manhwa=self.kwargs["manhwa_pk"])
            )
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
