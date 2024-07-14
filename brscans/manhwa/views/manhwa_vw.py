from hashlib import sha256
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q

from brscans.manhwa.models import Manhwa
from brscans.manhwa.serializers import ManhwaSerializer
from brscans.manhwa.tasks.sync_chapters import sync_chapters
from brscans.wrapper.sources.Generic import Generic


class ManhwaViewSet(viewsets.ModelViewSet):
    queryset = Manhwa.objects.all()
    serializer_class = ManhwaSerializer
    permission_classes = []

    @action(detail=False, methods=["get"])
    def search(self, request):
        query = request.GET.get("query") or ""

        manhwas = Manhwa.objects.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(author__icontains=query)
            | Q(genres__name__icontains=query)
            | Q(source__name__icontains=query)
        )

        serializer = ManhwaSerializer(manhwas, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def sync(self, request):
        manhwas = Manhwa.objects.all()
        serializer = ManhwaSerializer(manhwas, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def download(self, request):
        link = request.query_params.get("link")
        identifier = sha256(link.encode("utf-8")).hexdigest()

        manhwa = Manhwa.objects.filter(identifier=identifier).first()

        if manhwa:
            serializer = self.serializer_class(manhwa)
            return Response(serializer.data)

        result = Generic.info(link, False)
        id = str(result.get("id")).encode("utf-8")

        manhwa = Manhwa.objects.create(
            external_id=id,
            hash_external_id=sha256(id).hexdigest(),
            title=result.get("title"),
            source=result.get("url"),
            description=result.get("summary"),
            identifier=identifier,
        )
        sync_chapters(manhwa.pk)

        return Response(self.serializer_class(manhwa).data)
