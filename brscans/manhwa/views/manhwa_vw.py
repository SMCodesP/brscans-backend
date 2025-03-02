from django.http import FileResponse
from hashlib import sha256
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Prefetch
from django.db.models.expressions import RawSQL

from brscans.manhwa.models import Chapter, ImageVariants, Manhwa
from brscans.manhwa.serializers import ManhwaDetailSerializer, ManhwaSerializer
from brscans.manhwa.tasks.images_variants import add_original_image_variant
from brscans.manhwa.tasks.sync_chapter import sync_chapter, sync_chapter_fix
from brscans.manhwa.tasks.sync_chapters import sync_chapters
from brscans.pagination import TotalPagination

# from brscans.utils.anime4k import Anime4k
from brscans.wrapper import sources
from brscans.wrapper.sources.Generic import Generic
from brscans.wrapper.sources.KingOfShojo import KingOfShojo


class ManhwaViewSet(viewsets.ModelViewSet):
    queryset = (
        Manhwa.objects.all()
        .order_by("-id")
        .select_related("thumbnail")
        .prefetch_related("genres")
    )
    serializer_class = ManhwaSerializer
    permission_classes = []
    pagination_class = TotalPagination

    def retrieve(self, request, *args, **kwargs):
        self.queryset = self.queryset.prefetch_related(
            Prefetch(
                "chapters",
                queryset=Chapter.objects.all()
                .annotate(
                    slug_number=RawSQL("CAST(SUBSTRING(slug FROM 9) AS INTEGER)", [])
                )
                .order_by("slug_number"),
            ),
            "chapters__pages",
            "chapters__pages__images",
        )
        self.serializer_class = ManhwaDetailSerializer
        return super().retrieve(request, *args, **kwargs)

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

    @action(detail=True, methods=["get"])
    def count_fix_caps(self, request, pk=None):
        chapters = Chapter.objects.filter(
            (
                Q(pages__isnull=True)
                | Q(pages__images__isnull=True)
                | Q(pages__images__translated__isnull=True)
                | Q(pages__images__original__isnull=True)
                | Q(pages__images__original="")
                | Q(pages__images__translated="")
            ),
            manhwa=pk,
        )

        return Response({"count": chapters.count()})

    @action(detail=True, methods=["get"])
    def fix_caps(self, request, pk=None):
        chapters = Chapter.objects.filter(
            (
                Q(pages__isnull=True)
                | Q(pages__images__isnull=True)
                | Q(pages__images__translated__isnull=True)
                | Q(pages__images__original__isnull=True)
                | Q(pages__images__original="")
                | Q(pages__images__translated="")
            ),
            manhwa=pk,
        )

        for chapter in chapters:
            chapter.pages.all().delete()
            sync_chapter(chapter.pk, pk)

        return Response({"message": f"Corrigindo {chapters.count()} capítulos."})

    @action(detail=True, methods=["get"])
    def fix(self, request, pk=None):
        manhwa = Manhwa.objects.get(pk=pk)

        chapters = Chapter.objects.filter(manhwa=manhwa)

        results = []

        for chapter in chapters:
            results.append(sync_chapter_fix(chapter.pk))

        return Response(results)

    @action(detail=False, methods=["get"])
    def download(self, request):
        link = request.query_params.get("link")
        identifier = sha256(link.encode("utf-8")).hexdigest()

        manhwa = Manhwa.objects.filter(identifier=identifier).first()

        if manhwa:
            sync_chapters(manhwa.pk)
            serializer = self.serializer_class(manhwa)
            return Response(serializer.data)

        Source: Generic = sources.get_source_by_link(link)
        result = Source.info(link, capthers=True)

        id = str(result.get("id")).encode("utf-8")

        manhwa = Manhwa.objects.create(
            external_id=id,
            hash_external_id=sha256(id).hexdigest(),
            title=result.get("title"),
            source=result.get("url"),
            description=result.get("summary"),
            identifier=identifier,
        )
        thumbnail = ImageVariants.objects.create()
        manhwa.thumbnail = thumbnail
        manhwa.save()

        add_original_image_variant(
            thumbnail.pk, result.get("image"), ["chapters", str(manhwa.pk)], False
        )
        sync_chapters(manhwa.pk)

        return Response(self.serializer_class(manhwa).data)

    # @action(detail=False, methods=["get"])
    # def anime4k(self, request):
    #     image = request.query_params.get("image")
    #     anime4k = Anime4k()
    #     path = anime4k.upscale_remote_image(image)

    #     return FileResponse(open(path, "rb"), content_type="image/png")
