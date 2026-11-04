import os

from django.conf import settings
from django.core.files.storage import default_storage
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.response import Response

from brscans.manhwa.models import ImageVariants
from brscans.manhwa.serializers import VariantsSerializer
from brscans.pagination import TotalPagination
from brscans.utils.image_contract import normalize_image_path

EDITABLE = ("raw", "original", "translated")


class ReadOrStaffWrite(BasePermission):
    """GET livre (leitura de página usa). Escrita só com token de staff —
    o tradutor manda `Token` de um usuário is_staff no callback."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        user = request.user
        return bool(user and user.is_authenticated and user.is_staff)


class VariantsEditSerializer(serializers.ModelSerializer):
    """Aceita path do storage ('chapters/1/x.webp') ou URL absoluta do CDN."""

    raw = serializers.CharField(required=False, allow_blank=True)
    original = serializers.CharField(required=False, allow_blank=True)
    translated = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        for field in EDITABLE:
            if field not in attrs:
                continue
            value = (attrs[field] or "").strip()
            if not value:
                attrs[field] = ""
                continue
            try:
                path = normalize_image_path(value, settings.MEDIA_URL)
            except ValueError as exc:
                raise serializers.ValidationError({field: [str(exc)]})
            if not default_storage.exists(path):
                raise serializers.ValidationError(
                    {field: [f"Arquivo não encontrado: {path}"]}
                )
            attrs[field] = path
        return attrs

    def update(self, instance, validated_data):
        new = validated_data.get("translated")
        if new is not None and new != (
            instance.translated.name if instance.translated else ""
        ):
            # não perde a anterior e fica registrado que foi edição manual
            if instance.translated:
                instance.previous_translated = instance.translated.name
            instance.manual_translated = True
        return super().update(instance, validated_data)

    class Meta:
        model = ImageVariants
        fields = ("id",) + EDITABLE


class ImageVariantViewSet(viewsets.ModelViewSet):
    serializer_class = VariantsSerializer
    queryset = ImageVariants.objects.all()
    pagination_class = TotalPagination
    permission_classes = [ReadOrStaffWrite]

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = VariantsEditSerializer(
            instance, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # cache temporário do tradutor para esta variant ficou inválido
        if "translated" in serializer.validated_data:
            self._drop_translator_cache(instance.pk)
        return Response(VariantsSerializer(instance).data)

    @staticmethod
    def _drop_translator_cache(variant_id):
        try:
            from pymongo import MongoClient

            client = MongoClient(os.environ["MONGODB_URI"])
            client["brscans-ia"]["blk_list"].delete_many(
                {"image_id": int(variant_id)}
            )
        except Exception as e:
            print(
                f"Erro ao deletar blk_list temporario para variant {variant_id}:",
                e,
            )

    @action(detail=True, methods=["post"], url_path="use-original")
    def use_original(self, request, pk=None):
        variant = self.get_object()
        if not variant.original:
            return Response(
                {"detail": "Esta page não tem original."}, status=400
            )
        path = variant.original.name
        if not default_storage.exists(path):
            return Response(
                {"detail": f"Arquivo não encontrado: {path}"}, status=400
            )
        if variant.translated and variant.translated.name != path:
            variant.previous_translated = variant.translated.name
        variant.translated = path
        variant.manual_translated = True
        variant.save()
        return Response(VariantsSerializer(variant).data)
