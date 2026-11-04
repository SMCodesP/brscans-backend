"""Contagem de queries das rotas públicas: `quantity_merged` vinha de um SUM
por capítulo (N+1). O número de queries não pode crescer com o volume."""

from django.test import TestCase
from rest_framework.test import APIClient

from brscans.manhwa.models import Chapter, Genre, ImageVariants, Manhwa, Page


class SerializerQueryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.genre = Genre.objects.create(name="Ação", slug="acao")

    def make_manhwa(self, title, chapters=3, pages=2, merged=2):
        manhwa = Manhwa.objects.create(
            title=title, status="ongoing", description="", thumbnail=None
        )
        manhwa.genres.add(self.genre)
        for number in range(1, chapters + 1):
            chapter = Chapter.objects.create(
                title=f"Cap {number}", slug=f"cap-{number}", manhwa=manhwa
            )
            for order in range(pages):
                Page.objects.create(
                    chapter=chapter,
                    images=ImageVariants.objects.create(),
                    order=order,
                    quantity_merged=merged,
                )
        return manhwa

    def test_list_nao_cresce_com_o_numero_de_manhwas(self):
        manhwa = self.make_manhwa("Um")
        with self.assertNumQueries(self.list_queries()) as one:
            self.client.get("/manhwas/")
        one_count = len(one.captured_queries)

        for title in ("Dois", "Tres", "Quatro", "Cinco"):
            self.make_manhwa(title)

        self.client.get("/manhwas/")  # aquece nada: cada request é nova
        with self.assertNumQueries(one_count):
            response = self.client.get("/manhwas/?limit=100")

        # Mantém o contrato do JSON (o front consome latest_chapters).
        results = response.json()["results"]
        latest = next(m for m in results if m["id"] == manhwa.id)[
            "latest_chapters"
        ]
        self.assertEqual(latest[0]["quantity_merged"], 4)

    def test_detalhe_do_capitulo_traz_os_vizinhos_anotados(self):
        manhwa = self.make_manhwa("Cap", chapters=10, pages=2, merged=3)
        chapter = manhwa.chapters.get(slug="cap-5")

        # As 4 queries fixas (capítulo, páginas, variantes, lista de irmãos);
        # o SUM de cada vizinho vem da anotação, não de uma query por capítulo.
        with self.assertNumQueries(4):
            response = self.client.get(f"/chapters/{chapter.id}/")

        data = response.json()
        self.assertEqual(data["quantity_merged"], 6)
        self.assertEqual(data["previous"]["slug"], "cap-4")
        self.assertEqual(data["next"]["slug"], "cap-6")
        self.assertEqual(data["next"]["quantity_merged"], 6)

    def list_queries(self):
        return self._count(lambda: self.client.get("/manhwas/"))

    def _count(self, call):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as captured:
            call()
        return len(captured)
