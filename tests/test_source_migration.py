"""Migração de fonte: regras 1-6 do spec, sem rede.

`migrate_manhwa` é o caminho do painel e do command automático; os testes do
painel cobrem só a casca HTTP (contrato do orquestrador).
"""

from io import StringIO
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from brscans.manhwa import source_migration
from brscans.manhwa.models import Chapter, Manhwa
from brscans.manhwa.source_migration import MigrationError, migrate_manhwa


SEARCH = [
    {
        "id": "x",
        "title": "Teste",
        "url": "https://novo.com/manga/x/",
        "image": "https://novo.com/capa.jpg",
    },
]


def source(chapters):
    class FakeSource:
        def __init__(self, url, headers=None):
            self.url = url

        info = staticmethod(
            lambda url, capthers=False: {"id": "novo", "url": url}
        )
        chapters = staticmethod(lambda manhwa: chapters)
        search = staticmethod(lambda query: SEARCH)

    return FakeSource


CHAPS = [
    {"id": "c-1", "title": "Capítulo 1", "url": "https://novo.com/cap-1/"},
    {"id": "c-2", "title": "Capítulo 2", "url": "https://novo.com/cap-2/"},
    {"id": "c-3", "title": "Capítulo 3", "url": "https://novo.com/cap-3/"},
]


class MigrationRuleTests(TestCase):
    def setUp(self):
        self.manhwa = Manhwa.objects.create(
            title="Teste",
            status="ongoing",
            source="https://velho.com/manga/x/",
            identifier="velho",
            external_id="1",
        )
        self.c1 = Chapter.objects.create(
            title="Cap 1",
            slug="vidro-1",
            manhwa=self.manhwa,
            source="https://velho.com/cap-1/",
        )
        self.c2 = Chapter.objects.create(
            title="Cap 2",
            slug="vidro-2",
            manhwa=self.manhwa,
            source="https://velho.com/cap-2/",
        )
        self.sem_par = Chapter.objects.create(
            title="Cap 9",
            slug="vidro-9",
            manhwa=self.manhwa,
            source="https://velho.com/cap-9/",
        )

    def migrate(self, chapters=CHAPS):
        with (
            mock.patch.object(
                source_migration,
                "get_source_by_link",
                lambda url: source(chapters),
            ),
            mock.patch.object(source_migration, "check_manhwa_source") as check,
        ):
            result = migrate_manhwa(self.manhwa, "https://novo.com/manga/x/")
        return result, check

    def test_same_manhwa_and_matches_by_number(self):
        result, check = self.migrate()
        self.manhwa.refresh_from_db()
        self.assertEqual(self.manhwa.source, "https://novo.com/manga/x/")
        self.assertEqual(result["matched"], 2)
        self.assertEqual(result["created"], 1)
        self.assertEqual(result["unmatched"], ["Cap 9"])
        self.c1.refresh_from_db()
        self.assertEqual(self.c1.source, "https://novo.com/cap-1/")
        self.assertEqual(self.c1.slug, "c-1")  # dedupe do cron pelo slug
        # regra 5: capítulo sem par fica como está e é reportado
        self.sem_par.refresh_from_db()
        self.assertEqual(self.sem_par.source, "https://velho.com/cap-9/")
        check.assert_called_once_with(self.manhwa.pk)

    def test_regra_4_capitulo_novo_entra_pelo_sync(self):
        self.migrate()
        novo = Chapter.objects.get(manhwa=self.manhwa, slug="c-3")
        self.assertFalse(novo.pages.exists())  # páginas ficam para o sync
        self.assertEqual(Chapter.objects.filter(manhwa=self.manhwa).count(), 4)

    def test_source_falhando_nao_altera_nada(self):
        with mock.patch.object(
            source_migration,
            "get_source_by_link",
            lambda url: SimpleNamespace(
                info=lambda *a, **k: {}, chapters=mock.Mock(side_effect=OSError)
            ),
        ):
            with self.assertRaises(MigrationError):
                migrate_manhwa(self.manhwa, "https://novo.com/manga/x/")
        self.manhwa.refresh_from_db()
        self.assertEqual(self.manhwa.source, "https://velho.com/manga/x/")

    def test_zero_capitulos_nao_altera_nada(self):
        with self.assertRaises(MigrationError):
            self.migrate([])
        self.manhwa.refresh_from_db()
        self.assertEqual(self.manhwa.source, "https://velho.com/manga/x/")

    def test_identifier_vem_da_url_canonica(self):
        """Fonte que redireciona: o identifier tem que casar com a URL gravada."""
        manhwa = Manhwa.objects.create(
            title="Redirect",
            status="ongoing",
            source="https://velho.com/y/",
        )
        final = "https://novo.com/manga/y/"

        class Redirects:
            def __init__(self, url, headers=None):
                pass

            info = staticmethod(lambda url, capthers=False: {"url": final})
            chapters = staticmethod(lambda manhwa: CHAPS)

        with (
            mock.patch.object(
                source_migration, "get_source_by_link", lambda url: Redirects
            ),
            mock.patch.object(source_migration, "check_manhwa_source"),
        ):
            migrate_manhwa(manhwa, "https://novo.com/velho-endereco/")
        manhwa.refresh_from_db()
        self.assertEqual(manhwa.source, final)
        self.assertEqual(manhwa.identifier, migrate_identifier(final))

    def test_url_de_outro_manga_e_recusada(self):
        Manhwa.objects.create(
            title="Outro",
            status="ongoing",
            source="https://novo.com/manga/y/",
            identifier=migrate_identifier("https://novo.com/manga/y/"),
        )
        with self.assertRaises(MigrationError):
            migrate_manhwa(self.manhwa, "https://novo.com/manga/y/")
        self.manhwa.refresh_from_db()
        self.assertEqual(self.manhwa.source, "https://velho.com/manga/x/")

    def test_migrar_duas_vezes_nao_muda_nada(self):
        self.migrate()
        before = list(
            Chapter.objects.filter(manhwa=self.manhwa).values_list(
                "pk", "slug", "source"
            )
        )
        result, _ = self.migrate()
        after = list(
            Chapter.objects.filter(manhwa=self.manhwa).values_list(
                "pk", "slug", "source"
            )
        )
        self.assertEqual(before, after)
        self.assertEqual(result["created"], 0)


def migrate_identifier(url):
    from hashlib import sha256

    return sha256(url.encode("utf-8")).hexdigest()


class MigrationCommandTests(TestCase):
    def test_dry_run_imprime_o_plano_e_nao_altera(self):
        manhwa = Manhwa.objects.create(
            title="Teste",
            status="ongoing",
            source="https://velho.com/x/",
            source_status="offline",
        )
        with (
            mock.patch.object(
                source_migration,
                "get_source_by_link",
                lambda url: source(CHAPS),
            ),
            mock.patch(
                "brscans.manhwa.management.commands.migrate_sources.searchable_sources",
                {"novo.com": source(CHAPS)},
            ),
        ):
            call_command("migrate_sources", "--dry-run", stdout=StringIO())
        manhwa.refresh_from_db()
        self.assertEqual(manhwa.source, "https://velho.com/x/")
        self.assertEqual(manhwa.chapters.count(), 0)


class PanelMigrationContractTests(TestCase):
    """Casca HTTP: contrato do orquestrador (200/400/502)."""

    def setUp(self):
        from rest_framework.test import APIClient

        staff = User.objects.create_user("s", password="x", is_staff=True)
        self.client = APIClient()
        self.client.force_authenticate(staff)
        self.manhwa = Manhwa.objects.create(title="Teste", status="ongoing")

    def test_sources_list(self):
        response = self.client.get("/panel/sources/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data[0]), {"name", "host"})

    def test_search_unknown_source_404(self):
        response = self.client.get("/panel/sources/nada.com/search/?q=x")
        self.assertEqual(response.status_code, 404)

    def test_search_returns_thumbnail(self):
        with mock.patch(
            "brscans.manhwa.views.panel.get_searchable_source",
            return_value=source([]),
        ):
            response = self.client.get("/panel/sources/novo.com/search/?q=x")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.data["results"][0]), {"title", "url", "thumbnail"}
        )
        self.assertEqual(
            response.data["results"][0]["thumbnail"], "https://novo.com/capa.jpg"
        )

    def test_search_timeout_is_502(self):
        import time

        from brscans.manhwa.views.panel import PanelSourceView

        class Slow:
            def __init__(self, url, headers=None):
                pass

            search = staticmethod(lambda query: time.sleep(1) or [])

        with (
            mock.patch(
                "brscans.manhwa.views.panel.get_searchable_source",
                return_value=Slow,
            ),
            mock.patch.object(PanelSourceView, "SEARCH_TIMEOUT", 0.05),
        ):
            response = self.client.get("/panel/sources/slow.com/search/?q=x")
        self.assertEqual(response.status_code, 502)
        self.assertIn("detail", response.data)

    def test_migrate_success(self):
        with mock.patch(
            "brscans.manhwa.views.panel.migrate_manhwa",
            return_value={
                "source": "u",
                "matched": 1,
                "created": 0,
                "unmatched": [],
            },
        ):
            response = self.client.post(
                f"/panel/manhwas/{self.manhwa.pk}/migrate/", {"url": "u"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.data), {"source", "matched", "created", "unmatched"}
        )

    def test_migrate_bad_request(self):
        with mock.patch(
            "brscans.manhwa.views.panel.migrate_manhwa",
            side_effect=MigrationError("url de outro manga"),
        ):
            response = self.client.post(
                f"/panel/manhwas/{self.manhwa.pk}/migrate/", {"url": "u"}
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.data)

    def test_migrate_source_down_is_502(self):
        with mock.patch(
            "brscans.manhwa.views.panel.migrate_manhwa",
            side_effect=MigrationError("fora", upstream=True),
        ):
            response = self.client.post(
                f"/panel/manhwas/{self.manhwa.pk}/migrate/", {"url": "u"}
            )
        self.assertEqual(response.status_code, 502)

    def test_ordering_problems_puts_unhealthy_first(self):
        Manhwa.objects.create(title="Ok", status="ongoing", source_status="ok")
        Manhwa.objects.create(
            title="Morto", status="ongoing", source_status="offline"
        )
        response = self.client.get(
            "/panel/manhwas/?ordering=problems&limit=100"
        )
        titles = [row["title"] for row in response.data["results"]]
        self.assertLess(titles.index("Morto"), titles.index("Ok"))
        self.assertLess(
            titles.index("Teste"), titles.index("Ok")
        )  # sem status = problema
