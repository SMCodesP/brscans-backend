from hashlib import sha256

from django.db.models import Count, Prefetch, Q
from django.db.models.expressions import RawSQL
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from brscans.manhwa.models import (
    Chapter,
    Genre,
    ImageVariants,
    Manhwa,
    Page,
    ReadChapter,
    ReadingHistory,
)
from brscans.manhwa.serializers import (
    ChapterSerializer,
    GenreSerializer,
    ManhwaDetailSerializer,
    ManhwaSerializer,
    RecentChapterSerializer,
)
from brscans.manhwa.tasks.images_variants import add_original_image_variant
from brscans.manhwa.tasks.sync_chapter import (
    fix_pages,
    sync_chapter,
    sync_missing_original_pages,
)
from brscans.manhwa.tasks.sync_chapters import sync_chapters
from brscans.pagination import TotalPaginationManhwa

# from brscans.utils.anime4k import Anime4k
from brscans.wrapper import sources
from brscans.wrapper.sources.Generic import Generic


class ManhwaViewSet(viewsets.ModelViewSet):
    queryset = (
        Manhwa.objects.all()
        .order_by("-id")
        .select_related("thumbnail")
        .prefetch_related("genres", "chapters")
    )
    serializer_class = ManhwaSerializer
    pagination_class = TotalPaginationManhwa
    filter_backends = [SearchFilter, OrderingFilter, DjangoFilterBackend]
    search_fields = ["title", "description", "author", "source"]
    ordering = ["-id"]

    def list(self, request, *args, **kwargs):
        self.queryset = self.queryset.filter(is_nsfw=False)
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        self.queryset = self.queryset.prefetch_related(None).prefetch_related(
            "genres",
            Prefetch(
                "chapters",
                queryset=Chapter.objects.all()
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
            | Q(source__icontains=query)
        ).distinct()

        serializer = ManhwaSerializer(manhwas, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def recent_chapters(self, request):
        """Latest chapters with parent manga data for the homepage carousel."""
        limit = int(request.query_params.get("limit", 20))
        chapters = (
            Chapter.objects.filter(
                manhwa__is_nsfw=False,
                release_date__isnull=False,
            )
            .select_related("manhwa", "manhwa__thumbnail")
            .order_by("-release_date")[:limit]
        )
        serializer = RecentChapterSerializer(chapters, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def top(self, request):
        """Top mangas ranked by read chapters count (popularity proxy)."""
        limit = int(request.query_params.get("limit", 10))
        manhwas = (
            Manhwa.objects.filter(is_nsfw=False)
            .annotate(read_count=Count("read_chapters"))
            .select_related("thumbnail")
            .prefetch_related("genres")
            .order_by("-read_count", "-id")[:limit]
        )
        serializer = ManhwaSerializer(manhwas, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def progress(self, request, pk=None):
        if not request.user.is_authenticated:
            return Response({"error": "Autenticação necessária."}, status=401)

        manhwa = self.get_object()
        chapter_id = request.data.get("chapter_id")
        page_number = request.data.get("page_number", 1)

        if not chapter_id:
            return Response({"error": "chapter_id é obrigatório."}, status=400)

        ReadingHistory.objects.update_or_create(
            user=request.user,
            manhwa=manhwa,
            defaults={"chapter_id": chapter_id, "page_number": page_number},
        )
        return Response({"status": "Progresso salvo."})

    @action(detail=True, methods=["get"], url_path="read-chapters")
    def read_chapters(self, request, pk=None):
        if not request.user.is_authenticated:
            return Response([])

        manhwa = self.get_object()
        read_chapters = ReadChapter.objects.filter(
            user=request.user, manhwa=manhwa
        ).values_list("chapter_id", flat=True)

        return Response(list(read_chapters))

    @action(detail=False, methods=["get"], url_path="reading-history")
    def reading_history(self, request):
        if not request.user.is_authenticated:
            return Response([])

        limit = int(request.query_params.get("limit", 10))
        history = (
            ReadingHistory.objects.filter(user=request.user)
            .select_related("manhwa", "manhwa__thumbnail", "chapter")
            .order_by("-updated_at")[:limit]
        )

        data = []
        for h in history:
            data.append(
                {
                    "manhwa": ManhwaSerializer(h.manhwa).data,
                    "chapter": ChapterSerializer(h.chapter).data,
                    "page_number": h.page_number,
                    "updated_at": h.updated_at,
                }
            )

        return Response(data)

    @action(detail=False, methods=["get"])
    def genres(self, request):
        """List all available genres."""
        genres = Genre.objects.all().order_by("name")
        serializer = GenreSerializer(genres, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def count_fix_caps(self, request, pk=None):
        chapters = Chapter.objects.filter(
            (
                Q(pages__isnull=True)
                | Q(pages__images__isnull=True)
                | Q(pages__images__translated__isnull=True)
                | Q(pages__images__translated="")
            ),
            manhwa=pk,
            pages__images__original__isnull=False,
        ).distinct()

        for chapter in chapters[:20]:
            fix_pages(chapter.pk)

        return Response({"count": chapters.count()})

    @action(detail=True, methods=["get"])
    def count_pages_original(self, request, pk=None):
        page = Page.objects.filter(chapter__manhwa=pk).filter(
            (Q(images__original__isnull=True) | Q(images__original="")),
        )

        return Response({"count": page.count()})

    @action(detail=True, methods=["get"])
    def count_pages_to_fix(self, request, pk=None):
        page = Page.objects.filter(
            (
                Q(images__isnull=True)
                | Q(images__translated__isnull=True)
                | Q(images__translated="")
            ),
        )

        return Response({"count": page.count()})

    @action(detail=True, methods=["get"])
    def sync(self, request, pk=None):
        limit = request.query_params.get("limit", "5")
        manhwa = Manhwa.objects.get(pk=pk)
        sync_chapters(manhwa.pk, int(limit))
        serializer = self.serializer_class(manhwa)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def delete_chapter(self, request, pk=None):
        manhwa = Manhwa.objects.get(pk=pk)
        chapters = Chapter.objects.filter(manhwa=manhwa)
        chapters.delete()
        return Response({"message": "Chapter deleted successfully."})

    @action(detail=True, methods=["get"])
    def fix_caps(self, request, pk=None):
        chapters = Chapter.objects.filter(
            (
                Q(pages__images__original__isnull=True)
                | Q(pages__images__original="")
            ),
            manhwa=pk,
        ).distinct()[:20]

        for chapter in chapters:
            chapter.pages.all().delete()
            sync_chapter(chapter.pk, pk)

        serializer_data = ChapterSerializer(chapters, many=True).data

        return Response(
            {
                "message": f"Corrigindo {chapters.count()} capítulos.",
                "data": serializer_data,
            }
        )

    @action(detail=True, methods=["get"])
    def sync_missing_pages(self, request, pk=None):
        """
        Sincroniza páginas sem variant original.
        Faz o fetch novamente do capítulo e processa apenas as páginas faltantes.
        """
        # Buscar capítulos com páginas sem original
        chapters = (
            Chapter.objects.filter(manhwa=pk, pages__images__isnull=False)
            .filter(
                Q(pages__images__original__isnull=True)
                | Q(pages__images__original="")
            )
            .distinct()
        )

        # Limitar para processar em lotes
        limit = int(request.GET.get("limit", 10))
        chapters = chapters[:limit]

        results = []
        for chapter in chapters:
            sync_missing_original_pages(chapter.pk, pk)
            results.append(
                {
                    "chapter_id": chapter.pk,
                    "chapter_title": chapter.title,
                }
            )

        return Response(
            {
                "message": f"Sincronizando páginas faltantes de {chapters.count()} capítulos",
                "total_chapters": chapters.count(),
                "results": results,
            }
        )

    @action(detail=True, methods=["get"])
    def count_missing_original_pages(self, request, pk=None):
        """
        Conta quantas páginas estão sem variant original.
        """
        # Contar páginas sem original neste manhwa
        pages_without_original = (
            Page.objects.filter(chapter__manhwa=pk)
            .filter(Q(images__original__isnull=True) | Q(images__original=""))
            .count()
        )

        # Contar capítulos afetados
        chapters_affected = (
            Chapter.objects.filter(manhwa=pk, pages__images__isnull=False)
            .filter(
                Q(pages__images__original__isnull=True)
                | Q(pages__images__original="")
            )
            .distinct()
            .count()
        )

        # Detalhes por capítulo (primeiros 10)
        chapter_details = []
        chapters = (
            Chapter.objects.filter(manhwa=pk, pages__images__isnull=False)
            .filter(
                Q(pages__images__original__isnull=True)
                | Q(pages__images__original="")
            )
            .distinct()[:10]
        )

        for chapter in chapters:
            pages_missing = (
                Page.objects.filter(chapter=chapter)
                .filter(
                    Q(images__original__isnull=True) | Q(images__original="")
                )
                .count()
            )

            chapter_details.append(
                {
                    "chapter_id": chapter.pk,
                    "chapter_title": chapter.title,
                    "pages_without_original": pages_missing,
                }
            )

        return Response(
            {
                "total_pages_without_original": pages_without_original,
                "total_chapters_affected": chapters_affected,
                "sample_chapters": chapter_details,
            }
        )

    @action(detail=True, methods=["get"])
    def fix(self, request, pk=None):
        manhwa = Manhwa.objects.get(pk=pk)

        chapters = Chapter.objects.filter(manhwa=manhwa)

        results = []

        for chapter in chapters:
            results.append(sync_chapter(chapter.pk, pk))

        return Response(results)

    @action(detail=False, methods=["get"])
    def download(self, request):
        link = request.query_params.get("link")
        limit = request.query_params.get("limit", 5)
        identifier = sha256(link.encode("utf-8")).hexdigest()

        manhwa = Manhwa.objects.filter(identifier=identifier).first()

        if manhwa:
            print("manhwa found")
            sync_chapters(manhwa.pk, int(limit))

            serializer = self.serializer_class(manhwa)
            return Response(serializer.data)

        Source: Generic = sources.get_source_by_link(link)
        print("Source", Source)
        result = Source.info(link, capthers=False)
        print("result", result)

        id = str(result.get("id")).encode("utf-8")

        manhwa = Manhwa.objects.create(
            external_id=result.get("id"),
            hash_external_id=sha256(id).hexdigest(),
            title=result.get("title"),
            slug=result.get("slug", None),
            source=result.get("url"),
            description=result.get("summary"),
            identifier=identifier,
        )
        thumbnail = ImageVariants.objects.create()
        manhwa.thumbnail = thumbnail
        manhwa.save()

        print(manhwa.pk)
        add_original_image_variant(
            thumbnail.pk,
            result.get("image"),
            ["chapters", str(manhwa.pk)],
            False,
        )
        sync_chapters(manhwa.pk, int(limit))

        return Response(self.serializer_class(manhwa).data)

    # @action(detail=False, methods=["get"])
    # def anime4k(self, request):
    #     image = request.query_params.get("image")
    #     anime4k = Anime4k()
    #     path = anime4k.upscale_remote_image(image)

    #     return FileResponse(open(path, "rb"), content_type="image/png")
