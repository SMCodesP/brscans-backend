from rest_framework import viewsets

from brscans.manhwa.models import ImageVariants
from brscans.manhwa.serializers import VariantsSerializer, VariantsUpdateSerializer
from brscans.pagination import TotalPagination


class ImageVariantViewSet(viewsets.ModelViewSet):
    serializer_class = VariantsSerializer
    queryset = ImageVariants.objects.all()
    pagination_class = TotalPagination
    authentication_classes = []
    permission_classes = []

    def partial_update(self, request, *args, **kwargs):
        self.serializer_class = VariantsUpdateSerializer
        return super().partial_update(request, *args, **kwargs)
