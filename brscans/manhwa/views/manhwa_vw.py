from hashlib import sha256

from django.db.models import Count, Max, Prefetch, Q
from django.db.models.expressions import RawSQL
from django.db.models.functions import Coalesce
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from brscans.manhwa.models import (
    Chapter,
    Genre,
    Manhwa,
    ReadChapter,
    ReadingHistory,
)
from brscans.manhwa.serializers import (
    ChapterSerializer,
    GenreSerializer,
    ManhwaDetailSerializer,
    ManhwaSerializer,
    RecentChapterSerializer,
    with_quantity_merged,
)
from brscans.manhwa.tasks.sync_chapter import sync_chapter
from brscans.manhwa.tasks.sync_chapters import sync_chapters
from brscans.manhwa.tasks.sync_workers import repair_pages
from brscans.manhwa.work import (
    pending_counts_bulk,
    process_chapter,
)
from brscans.pagination import TotalPaginationManhwa


class ManhwaViewSet(viewsets.ModelViewSet):
    # O prefetch anotado de capítulos só entra em `list`: o cache de `chapters`
    # é compartilhado com `latest_chapters`, e num queryset global ele
    # carregaria todos os capítulos (e páginas) de todas as manhwas.
    queryset = (
        Manhwa.objects.all()
        .order_by("-id")
        .select_related("thumbnail")
        .prefetch_related("genres")
    )
    serializer_class = ManhwaSerializer
    pagination_class = TotalPaginationManhwa
    filter_backends = [SearchFilter, OrderingFilter, DjangoFilterBackend]
    search_fields = ["title", "description", "author", "source"]
    ordering = []

    def list(self, request, *args, **kwargs):
        queryset = self.queryset.filter(is_nsfw=False)

        # Default ordering by recent chapter activity.
        if not request.query_params.get("ordering"):
            queryset = (
                queryset.filter(chapters__isnull=False)
                .annotate(latest_release=Max("chapters__release_date"))
                .annotate(latest_created=Max("chapters__created_at"))
                .annotate(
                    latest_activity=Coalesce(
                        "latest_release", "latest_created"
                    )
                )
                .filter(latest_activity__isnull=False)
                .order_by("-latest_activity", "-id")
            )

        # `latest_chapters` lê o cache de `chapters`; anotado, é 1 SUM por
        # manhwa em vez de 2 aggregate avulsos por item da página.
        self.queryset = queryset.prefetch_related(
            Prefetch(
                "chapters", queryset=with_quantity_merged(Chapter.objects.all())
            )
        )
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        # O detalhe não usa chapter.pages (o front busca o capítulo na leitura),
        # por isso não há prefetch de páginas aqui.
        self.queryset = self.queryset.prefetch_related(
            "genres",
            Prefetch(
                "chapters",
                queryset=with_quantity_merged(Chapter.objects.all())
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
        )
        self.serializer_class = ManhwaDetailSerializer
        return super().retrieve(request, *args, **kwargs)

    @action(detail=False, methods=["get"])
    def search(self, request):
        query = request.GET.get("query") or ""

        manhwas = (
            Manhwa.objects.filter(
                Q(title__icontains=query)
                | Q(description__icontains=query)
                | Q(author__icontains=query)
                | Q(genres__name__icontains=query)
                | Q(source__icontains=query)
            )
            .distinct()
            .select_related("thumbnail")
            .prefetch_related(
                "genres",
                Prefetch(
                    "chapters",
                    queryset=with_quantity_merged(Chapter.objects.all()),
                ),
            )
        )

        serializer = ManhwaSerializer(manhwas, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def recent_chapters(self, request):
        """Latest chapters with parent manga data for the homepage carousel."""
        limit = int(request.query_params.get("limit", 20))
        chapters = (
            Chapter.objects.filter(
                manhwa__is_nsfw=False,
            )
            .annotate(sort_date=Coalesce("release_date", "created_at"))
            .filter(sort_date__isnull=False)
            .select_related("manhwa", "manhwa__thumbnail")
            .order_by("-sort_date", "-id")[:limit]
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
            .prefetch_related(
                "genres",
                Prefetch(
                    "chapters",
                    queryset=with_quantity_merged(Chapter.objects.all()),
                ),
            )
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
            .select_related("manhwa", "manhwa__thumbnail")
            .prefetch_related(
                Prefetch(
                    "chapter",
                    queryset=with_quantity_merged(Chapter.objects.all()),
                ),
                Prefetch(
                    "manhwa__chapters",
                    queryset=with_quantity_merged(Chapter.objects.all()),
                ),
            )
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
        """Reparo manual (override): re-arma desistidos e ignora o backoff.

        Passa pela mesma trava/backoff/desistência do cron (`process_page` por
        página), só que com `force`. Continua respeitando a trava do capítulo
        de quem já está sendo processado — senão o botão duplicaria.
        """
        chapters = list(
            Chapter.objects.filter(manhwa=pk, pages__isnull=False).distinct()
        )
        counts = pending_counts_bulk([chapter.pk for chapter in chapters])
        pending = {
            chapter.pk: counts[chapter.pk][1]  # sem tradução
            for chapter in chapters
        }
        count = sum(pending.values())

        outcomes = {}
        for chapter in chapters[:80]:
            if not pending[chapter.pk]:
                continue
            outcome = process_chapter(
                chapter,
                lambda ch, needs_sync: repair_pages(ch.pk, force=True),
                force=True,
            )
            outcomes[outcome] = outcomes.get(outcome, 0) + 1

        print("Quantidade de paginas para serem traduzidas", count)

        return Response(
            {
                "count": count,
                "dispatched": outcomes.get("dispatched", 0),
                "outcomes": outcomes,
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
        from brscans.manhwa.tasks.panel import create_manhwa

        link = request.query_params.get("link")
        identifier = sha256(link.encode("utf-8")).hexdigest()
        limit = int(request.query_params.get("limit", 5))

        manhwa = Manhwa.objects.filter(identifier=identifier).first()
        if manhwa:
            sync_chapters(manhwa.pk, limit)
            return Response(self.serializer_class(manhwa).data)

        result = create_manhwa(link, limit)
        if not isinstance(result, dict):
            # Dentro da Lambda o @task só enfileira o invoke.
            return Response({"status": "queued"}, status=202)
        return Response(result)
