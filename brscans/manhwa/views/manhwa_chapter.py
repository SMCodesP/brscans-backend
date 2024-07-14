from rest_framework import viewsets

from brscans.manhwa.models import Chapter
from brscans.manhwa.serializers import ChapterSerializer


class ManhwaChapterViewSet(viewsets.ModelViewSet):
    serializer_class = ChapterSerializer
    queryset = Chapter.objects.all()

    def get_queryset(self):
        return Chapter.objects.filter(manhwa=self.kwargs["manhwa_pk"])
