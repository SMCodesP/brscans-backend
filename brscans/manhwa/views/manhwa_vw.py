from hashlib import sha256

from django.db.models import Prefetch, Q
from django.db.models.expressions import RawSQL
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from brscans.manhwa.models import Chapter, ImageVariants, Manhwa, Page
from brscans.manhwa.serializers import (
    ChapterSerializer,
    ManhwaDetailSerializer,
    ManhwaSerializer,
)
from brscans.manhwa.tasks.images_variants import add_original_image_variant
from brscans.manhwa.tasks.sync_chapter import fix_pages, sync_chapter, sync_chapter_fix, sync_missing_original_pages
from brscans.manhwa.tasks.sync_chapters import sync_chapters
from brscans.pagination import TotalPagination

# from brscans.utils.anime4k import Anime4k
from brscans.wrapper import sources
from brscans.wrapper.sources.Generic import Generic


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

    def list(self, request, *args, **kwargs):
        self.queryset = self.queryset.filter(is_nsfw=False)
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        self.queryset = self.queryset.prefetch_related(
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
            (
                Q(images__original__isnull=True)
                | Q(images__original="")
            ),
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
        manhwa = Manhwa.objects.get(pk=pk)
        sync_chapters(manhwa.pk)
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
        chapters = Chapter.objects.filter(
            manhwa=pk,
            pages__images__isnull=False
        ).filter(
            Q(pages__images__original__isnull=True) | Q(pages__images__original="")
        ).distinct()
        
        # Limitar para processar em lotes
        limit = int(request.GET.get('limit', 10))
        chapters = chapters[:limit]
        
        results = []
        for chapter in chapters:
            sync_missing_original_pages(chapter.pk, pk)
            results.append({
                "chapter_id": chapter.pk,
                "chapter_title": chapter.title,
            })
        
        return Response({
            "message": f"Sincronizando páginas faltantes de {chapters.count()} capítulos",
            "total_chapters": chapters.count(),
            "results": results
        })

    @action(detail=True, methods=["get"])
    def count_missing_original_pages(self, request, pk=None):
        """
        Conta quantas páginas estão sem variant original.
        """
        # Contar páginas sem original neste manhwa
        pages_without_original = Page.objects.filter(
            chapter__manhwa=pk
        ).filter(
            Q(images__original__isnull=True) | Q(images__original="")
        ).count()
        
        # Contar capítulos afetados
        chapters_affected = Chapter.objects.filter(
            manhwa=pk,
            pages__images__isnull=False
        ).filter(
            Q(pages__images__original__isnull=True) | Q(pages__images__original="")
        ).distinct().count()
        
        # Detalhes por capítulo (primeiros 10)
        chapter_details = []
        chapters = Chapter.objects.filter(
            manhwa=pk,
            pages__images__isnull=False
        ).filter(
            Q(pages__images__original__isnull=True) | Q(pages__images__original="")
        ).distinct()[:10]
        
        for chapter in chapters:
            pages_missing = Page.objects.filter(
                chapter=chapter
            ).filter(
                Q(images__original__isnull=True) | Q(images__original="")
            ).count()
            
            chapter_details.append({
                "chapter_id": chapter.pk,
                "chapter_title": chapter.title,
                "pages_without_original": pages_missing
            })
        
        return Response({
            "total_pages_without_original": pages_without_original,
            "total_chapters_affected": chapters_affected,
            "sample_chapters": chapter_details
        })

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
