import threading
from urllib.parse import urljoin

from django.db.models import Case, Count, Q, When
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from brscans.manhwa.models import (
    Chapter,
    ImageVariants,
    Manhwa,
    Page,
    SourceStatus,
)
from brscans.manhwa.source_migration import MigrationError, migrate_manhwa
from brscans.manhwa.tasks.panel import (
    check_manhwa_source,
    create_manhwa,
    panel_fix_chapter,
    panel_sync_manhwa,
)
from brscans.pagination import TotalPagination
from brscans.wrapper.sources import get_searchable_source, searchable_sources


def _limit(value):
    """Capítulos por sync pedidos pelo painel: 1..50, default 5."""
    try:
        return max(1, min(int(value), 50))
    except (TypeError, ValueError):
        return 5


def _queued(result):
    """@task returns {task_id, status, Message} (or the plain return in Zappa)."""
    task_id = result.get("task_id") if isinstance(result, dict) else None
    return Response({"task": task_id, "status": "queued"}, status=202)


def problem_q(path: str = "") -> Q:
    """Page sem variant, sem original ou sem tradução. `path` vai até a Page
    ("pages__" no Chapter, "chapters__pages__" no Manhwa)."""
    return (
        Q(**{f"{path}images__isnull": True})
        | Q(**{f"{path}images__original__isnull": True})
        | Q(**{f"{path}images__original": ""})
        | Q(**{f"{path}images__translated__isnull": True})
        | Q(**{f"{path}images__translated": ""})
    )


# page traduzida é a que não tem nenhum desses problemas
TRANSLATED = ~problem_q("pages__")


class PanelManhwaSerializer(serializers.ModelSerializer):
    chapters_count = serializers.IntegerField(read_only=True)
    problem_pages = serializers.IntegerField(read_only=True)

    class Meta:
        model = Manhwa
        fields = (
            "id",
            "title",
            "source",
            "source_status",
            "source_detail",
            "source_checked_at",
            "source_http",
            "source_chapters",
            "chapters_count",
            "problem_pages",
        )


class PanelChapterSerializer(serializers.ModelSerializer):
    pages_count = serializers.IntegerField(read_only=True)
    translated_count = serializers.IntegerField(read_only=True)
    problem_pages = serializers.IntegerField(read_only=True)

    class Meta:
        model = Chapter
        fields = (
            "id",
            "title",
            "slug",
            "release_date",
            "quantity_pages",
            "pages_count",
            "translated_count",
            "problem_pages",
            "work_status",
            "work_attempts",
            "work_last_error",
        )


class PanelVariantsSerializer(serializers.ModelSerializer):
    original_path = serializers.SerializerMethodField()
    translated_path = serializers.SerializerMethodField()
    raw_path = serializers.SerializerMethodField()

    def _path(self, obj, field):
        value = getattr(obj, field)
        return value.name if value else None

    def get_original_path(self, obj):
        return self._path(obj, "original")

    def get_translated_path(self, obj):
        return self._path(obj, "translated")

    def get_raw_path(self, obj):
        return self._path(obj, "raw")

    class Meta:
        model = ImageVariants
        fields = (
            "raw",
            "original",
            "translated",
            "raw_path",
            "original_path",
            "translated_path",
            "previous_translated",
            "manual_translated",
        )


class PanelPageSerializer(serializers.ModelSerializer):
    images = PanelVariantsSerializer(read_only=True)
    reason = serializers.SerializerMethodField()

    def get_reason(self, obj):
        if obj.images is None:
            return "sem_variant"
        if not obj.images.original:
            return "sem_original"
        if not obj.images.translated:
            return "sem_traducao"
        return None

    class Meta:
        model = Page
        fields = (
            "id",
            "order",
            "chapter",
            "quantity_merged",
            "reason",
            "images",
        )


class PanelProblemSerializer(serializers.ModelSerializer):
    manhwa = serializers.SerializerMethodField()
    pages_count = serializers.IntegerField(read_only=True)
    translated_count = serializers.IntegerField(read_only=True)
    problem_pages = serializers.IntegerField(read_only=True)
    reason = serializers.SerializerMethodField()

    def get_manhwa(self, obj):
        return {"id": obj.manhwa_id, "title": obj.manhwa.title}

    def get_reason(self, obj):
        # 1º motivo em ordem de gravidade
        if not obj.pages_count:
            return "sem_pages"
        if not obj.translated_count:
            return "sem_traducao"
        return "erro_sync"

    class Meta:
        model = Chapter
        fields = (
            "id",
            "title",
            "manhwa",
            "pages_count",
            "translated_count",
            "problem_pages",
            "reason",
            "work_status",
            "work_attempts",
            "work_last_error",
        )


def chapter_counts(queryset):
    """Annotates pages_count/translated_count/problem_pages over Chapter."""
    return queryset.annotate(
        pages_count=Count("pages", distinct=True),
        translated_count=Count(
            "pages",
            filter=TRANSLATED,
            distinct=True,
        ),
        problem_pages=Count(
            "pages",
            filter=problem_q("pages__"),
            distinct=True,
        ),
    )


class PanelManhwaViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Admin panel routes for mangas. Staff only."""

    permission_classes = [IsAdminUser]
    pagination_class = TotalPagination
    serializer_class = PanelManhwaSerializer
    queryset = Manhwa.objects.all().order_by("-id")

    def create(self, request, *args, **kwargs):
        link = (request.data.get("link") or "").strip()
        if not link.startswith(("http://", "https://")):
            return Response(
                {"link": ["Informe a URL da página do mangá."]}, status=400
            )
        limit = _limit(request.data.get("limit"))
        is_nsfw = request.data.get("is_nsfw") is True
        return _queued(create_manhwa(link, limit, is_nsfw))

    @action(detail=True, methods=["post"], url_path="sync")
    def sync(self, request, pk=None):
        manhwa = self.get_object()
        return _queued(
            panel_sync_manhwa(manhwa.pk, _limit(request.data.get("limit")))
        )

    @action(detail=True, methods=["post"], url_path="check-source")
    def check_source(self, request, pk=None):
        manhwa = self.get_object()
        return _queued(check_manhwa_source(manhwa.pk))

    @action(detail=True, methods=["post"], url_path="migrate")
    def migrate(self, request, pk=None):
        try:
            result = migrate_manhwa(self.get_object(), request.data.get("url"))
        except MigrationError as exc:
            return Response(
                {"detail": str(exc)}, status=502 if exc.upstream else 400
            )
        return Response(result)

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("ordering") == "problems":
            # Problema = fonte que não está ok (inclui "sem fonte").
            qs = qs.annotate(
                _healthy=Case(
                    When(
                        source_status__in=[
                            SourceStatus.OK,
                            SourceStatus.REDIRECTED,
                        ],
                        then=1,
                    ),
                    default=0,
                )
            ).order_by("_healthy", "-id")
        query = params.get("q")
        if query:
            qs = qs.filter(
                Q(title__icontains=query)
                | Q(slug__icontains=query)
                | Q(source__icontains=query)
            )
        if params.get("source_status"):
            value = params["source_status"]
            if value == "never":
                qs = qs.filter(source_status__isnull=True)
            else:
                qs = qs.filter(source_status=value)
        return qs.annotate(
            chapters_count=Count("chapters", distinct=True),
            problem_pages=Count(
                "chapters__pages",
                filter=problem_q("chapters__pages__"),
                distinct=True,
            ),
        )

    @action(detail=True, methods=["get"])
    def chapters(self, request, pk=None):
        manhwa = self.get_object()
        qs = chapter_counts(Chapter.objects.filter(manhwa=manhwa)).order_by(
            "id"
        )
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(
            PanelChapterSerializer(page, many=True).data
        )


class PanelChapterViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAdminUser]
    pagination_class = TotalPagination
    serializer_class = PanelChapterSerializer
    queryset = Chapter.objects.select_related("manhwa").order_by("-id")

    def get_queryset(self):
        return chapter_counts(super().get_queryset())

    @action(detail=True, methods=["post"])
    def fix(self, request, pk=None):
        chapter = self.get_object()
        # @task: presign + POST ao ack de cada página roda no worker; o API
        # Gateway corta a resposta em 29 s.
        return _queued(panel_fix_chapter(chapter.pk))

    @action(detail=True, methods=["get"])
    def pages(self, request, pk=None):
        chapter = self.get_object()
        qs = (
            Page.objects.filter(chapter=chapter)
            .select_related("images")
            .order_by("order")
        )
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(
            PanelPageSerializer(page, many=True).data
        )


class PanelSourceView(APIView):
    """Fontes pesquisáveis e busca em uma só (o front chama uma por fonte).

    Sem fan-out aqui: o API Gateway corta a requisição em 29 s.
    """

    permission_classes = [IsAdminUser]
    SEARCH_TIMEOUT = 25  # API Gateway corta em 29 s

    def _search(self, search, query):
        """Roda `search(query)` com teto de tempo; `None` = estourou.

        O wrapper usa timeout=None, então uma resposta que não chega trava a
        request para sempre. Thread daemon (como health.py): a pendurada não
        segura a resposta, e um pool fixo ficaria sem vaga para as outras
        buscas que o front dispara em paralelo. A exceção da thread volta
        aqui: o `try` do caller já vira 502 com o motivo.
        """
        result, error = [], []

        def run():
            try:
                result.extend(search(query) or [])
            except Exception as exc:  # noqa: BLE001 - vira 502 no caller
                error.append(exc)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        thread.join(self.SEARCH_TIMEOUT)
        if error:
            raise error[0]
        return None if thread.is_alive() else result

    def get(self, request, name=None):
        if name is None:
            return Response(
                [{"name": host, "host": host} for host in searchable_sources]
            )

        Source = get_searchable_source(name)
        if Source is None:
            return Response({"detail": "Fonte desconhecida."}, status=404)
        query = (request.query_params.get("q") or "").strip()
        if not query:
            return Response({"source": name, "results": []})
        try:
            items = self._search(Source(f"https://{name}").search, query)
        except Exception as exc:  # noqa: BLE001 - a resposta é o relatório
            return Response(
                {"detail": f"{type(exc).__name__}: {exc}"[:300]}, status=502
            )
        if items is None:
            return Response(
                {
                    "detail": f"A fonte passou de {self.SEARCH_TIMEOUT}s "
                    "sem responder."
                },
                status=502,
            )

        return Response(
            {
                "source": name,
                "results": [
                    {
                        "title": item.get("title") or "",
                        # Webtoon devolve caminho relativo; a URL vai ao banco.
                        "url": urljoin(
                            f"https://{name}/", item.get("url") or ""
                        ),
                        "thumbnail": item.get("image") or item.get("thumbnail"),
                    }
                    for item in items
                ],
            }
        )


class PanelProblemViewSet(viewsets.ReadOnlyModelViewSet):
    """Chapters and pages that need a human looking at them."""

    permission_classes = [IsAdminUser]
    pagination_class = TotalPagination
    serializer_class = PanelProblemSerializer

    def get_queryset(self):
        qs = Chapter.objects.select_related("manhwa").order_by("-id")
        qs = qs.filter(problem_q("pages__"))
        if self.request.query_params.get("manhwa"):
            qs = qs.filter(manhwa_id=self.request.query_params["manhwa"])
        return chapter_counts(qs).distinct()

    @action(detail=False, methods=["get"])
    def pages(self, request):
        qs = (
            Page.objects.filter(problem_q())
            .select_related("images")
            .order_by("chapter_id", "order")
        )
        if request.query_params.get("chapter"):
            qs = qs.filter(chapter_id=request.query_params["chapter"])
        if request.query_params.get("manhwa"):
            qs = qs.filter(chapter__manhwa_id=request.query_params["manhwa"])
        return self.get_paginated_response(
            PanelPageSerializer(self.paginate_queryset(qs), many=True).data
        )
