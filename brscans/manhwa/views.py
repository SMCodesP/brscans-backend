from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from brscans.manhwa.models import Manhwa
from brscans.manhwa.serializers import ManhwaSerializer


class ManhwaViewSet(viewsets.ModelViewSet):
    queryset = Manhwa.objects.all()
    serializer_class = ManhwaSerializer
    permission_classes = []

    @action(detail=False, methods=["get"])
    def search(self, request):
        query = request.GET.get("query") or ""

        return Response("ok")
