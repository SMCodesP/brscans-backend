from rest_framework import viewsets

from brscans.manhwa.models import ImageVariants
from brscans.manhwa.serializers import VariantsSerializer
from brscans.pagination import TotalPagination


class ImageVariantViewSet(viewsets.ModelViewSet):
    serializer_class = VariantsSerializer
    queryset = ImageVariants.objects.all()
    pagination_class = TotalPagination
