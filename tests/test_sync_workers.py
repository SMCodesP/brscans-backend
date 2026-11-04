import os
import time
from unittest import mock

from django.test import TestCase, override_settings

from brscans.manhwa.models import SourceStatus
from brscans.manhwa.tasks import sync_workers


@override_settings(
    PUBLIC_MEDIA_LOCATION="media/",
    CHAPTER_RUN_SECONDS=120,
)
class HandlerTests(TestCase):
    def test_discovery_always_runs_even_with_nothing_pending(self):
        """Com tudo traduzido o cron ainda precisa achar capítulo novo."""
        with mock.patch.object(sync_workers, "close_finished", return_value=0):
            with mock.patch.object(
                sync_workers,
                "discover_new_chapters",
                return_value={"created": 1},
            ) as sync:
                with mock.patch.object(
                    sync_workers, "repair_pending_pages", return_value={}
                ):
                    with mock.patch.object(
                        sync_workers,
                        "drain_local_tasks",
                        return_value={"drained": True, "pending": 0},
                    ):
                        summary = sync_workers.handler()
        sync.assert_called_once()
        self.assertEqual(summary["sync"], {"created": 1})

    def test_run_reports_seconds_and_inflight(self):
        with mock.patch.object(sync_workers, "close_finished", return_value=1):
            with mock.patch.object(
                sync_workers, "discover_new_chapters", return_value={}
            ):
                with mock.patch.object(
                    sync_workers, "repair_pending_pages", return_value={}
                ) as repair:
                    with mock.patch.object(
                        sync_workers,
                        "drain_local_tasks",
                        return_value={"drained": True, "pending": 0},
                    ) as drain:
                        summary = sync_workers.handler()
        repair.assert_called_once()
        # A drenagem nunca passa do teto da execução.
        self.assertLessEqual(drain.call_args.args[0], 120)
        self.assertIn("seconds", summary)
        self.assertEqual(summary["inflight"], 0)

    def test_deadline_stops_repair_from_dispatching(self):
        with mock.patch.dict(os.environ, {"MONGODB_URI": "mongodb://stub"}):
            with mock.patch.object(sync_workers, "due_chapters") as due:
                due.return_value = [mock.Mock(pk=1), mock.Mock(pk=2)]
                with mock.patch.object(
                    sync_workers, "process_chapter"
                ) as process:
                    result = sync_workers.repair_pending_pages(
                        deadline=time.monotonic() - 1
                    )
        process.assert_not_called()
        self.assertEqual(result["deferred_chapters"], 2)

    def test_repair_disabled_loudly_without_mongodb_uri(self):
        with mock.patch.object(sync_workers, "due_chapters") as due:
            result = sync_workers.repair_pending_pages(
                deadline=time.monotonic() + 60
            )
        due.assert_not_called()
        self.assertIn("MONGODB_URI", result["disabled"])

    def test_dead_sources_are_not_queried(self):
        with mock.patch.object(sync_workers, "get_source_by_link") as source:
            summary = sync_workers.discover_new_chapters(
                deadline=time.monotonic() + 60
            )
        source.assert_not_called()
        self.assertEqual(
            summary, {"created": 0, "dispatched": 0, "matched": 0, "deferred": 0}
        )

    def test_dead_sources_list_covers_the_stuck_kinds(self):
        self.assertEqual(
            set(sync_workers.DEAD_SOURCES),
            {
                SourceStatus.NOT_FOUND,
                SourceStatus.DEAD,
                SourceStatus.OFFLINE,
                SourceStatus.BLOCKED,
                SourceStatus.NO_URL,
            },
        )


class DiscoveryDedupeTests(TestCase):
    """Fonte que troca o slug não pode virar capítulo vazio (02/11/2026)."""

    def setUp(self):
        from brscans.manhwa.models import Manhwa

        self.manhwa = Manhwa.objects.create(
            title="x",
            status="ongoing",
            description="d",
            source="https://kingofshojo.com/manga/x/",
        )
        # A fonte lista do mais novo ao antigo; o cron percorre ao contrário.
        self.listing = [
            {
                "id": "x-chapter-41",
                "title": "O Retorno da Espada #41 - Index 41%",
                "url": "https://k/x-41/",
            },
            {"id": "x-chapter-40", "title": "Capítulo 40", "url": "https://k/x-40/"},
        ]

    def run_discovery(self, listing):
        class FakeSource:
            chapters = staticmethod(lambda manhwa, throttle=None: listing)

        with mock.patch.object(
            sync_workers, "get_source_by_link", return_value=FakeSource
        ):
            with mock.patch.object(sync_workers, "process_chapter") as process:
                process.return_value = "dispatched"
                result = sync_workers.discover_new_chapters(
                    deadline=time.monotonic() + 60
                )
        return result, process

    def test_numero_ja_existente_nao_cria_duplicado(self):
        from brscans.manhwa.models import Chapter

        Chapter.objects.create(
            manhwa=self.manhwa,
            slug="outro-41",
            title="Outro #41 - Index%",
            source="https://k/outro-41/",
        )
        result, process = self.run_discovery(self.listing)

        self.assertEqual(result["created"], 1)  # só o 40
        self.assertEqual(result["matched"], 1)
        self.assertEqual(
            sorted(Chapter.objects.values_list("slug", flat=True)),
            ["outro-41", "x-chapter-40"],
        )
        process.assert_called_once()

    def test_mesma_url_nao_cria_duplicado(self):
        from brscans.manhwa.models import Chapter

        Chapter.objects.create(
            manhwa=self.manhwa,
            slug="outro-slug",
            title="Chapter 41",
            source="https://k/x-41/",
        )
        result, _ = self.run_discovery(self.listing)

        self.assertEqual(result["created"], 1)
        self.assertEqual(Chapter.objects.filter(manhwa=self.manhwa).count(), 2)

    def test_capitulo_de_verdade_continua_sendo_criado(self):
        result, _ = self.run_discovery(self.listing)

        self.assertEqual(result["created"], 2)
        self.assertEqual(result["matched"], 0)

    def test_fonte_renumerada_nao_zera_capitulo_real(self):
        """O banco tem o 40 com outro slug/URL: a fonte renumerou (40 -> 92),
        então o 40 que chega agora é capítulo novo de verdade."""
        from brscans.manhwa.models import Chapter

        Chapter.objects.create(
            manhwa=self.manhwa,
            slug="antigo-40",
            title="Chapter 40",
            source="https://k/antigo-40/",
        )
        result, _ = self.run_discovery(self.listing)

        self.assertEqual(result["created"], 2)
        self.assertEqual(result["matched"], 0)

    def test_mesmo_numero_mesmo_titulo_decorado_mesmo_slugs_diferentes(self):
        """A fonte trocou o slug da mesma URL: o 41 não pode nascer de novo."""
        from brscans.manhwa.models import Chapter

        Chapter.objects.create(
            manhwa=self.manhwa,
            slug="outro-slug",
            title="Algum #41 - Index%",
            source="https://k/x-41/",
        )
        result, _ = self.run_discovery(self.listing)

        self.assertEqual(result["created"], 1)  # só o 40
        self.assertEqual(result["matched"], 1)

    def test_dois_hosts_sao_consultados_e_o_sleep_e_o_do_host(self):
        from brscans.manhwa.models import Manhwa

        Manhwa.objects.create(
            title="y",
            status="ongoing",
            description="d",
            source="https://mangadass.com/manga/y",
        )
        sleeps = []

        def fake_sleep(seconds):
            sleeps.append(seconds)

        # O lançamento é o de produção; só o laço por host roda sem thread
        # (sqlite em memória não aceita escrita de outra thread).
        with mock.patch.dict(os.environ, {"BANCO_SINGLE_THREAD": "1"}):
            with mock.patch.object(
                sync_workers.time, "sleep", side_effect=fake_sleep
            ):
                with mock.patch.object(
                    sync_workers,
                    "get_source_by_link",
                    return_value=mock.Mock(
                        chapters=staticmethod(lambda manhwa, throttle=None: []),
                        __str__=lambda self: "fonte",
                    ),
                ):
                    sync_workers.discover_new_chapters(
                        deadline=time.monotonic() + 60
                    )

        # Um manhwa por host: nenhum host repete dentro do lote, então o
        # throttle não paga pausa à toa.
        self.assertEqual(sleeps, [])


@override_settings(PUBLIC_MEDIA_LOCATION="media/", REPAIR_PAGE_WORKERS=1)
class RepairChapterTaskTests(TestCase):
    def test_repair_runs_one_task_per_chapter_not_per_page(self):
        from brscans.manhwa.models import Chapter, ImageVariants, Manhwa, Page

        manhwa = Manhwa.objects.create(
            title="m", status="ongoing", description="d"
        )
        chapter = Chapter.objects.create(title="c", slug="c", manhwa=manhwa)
        for order in range(3):
            variant = ImageVariants.objects.create(original="o.webp")
            Page.objects.create(chapter=chapter, images=variant, order=order)

        sent = []
        with mock.patch.dict(os.environ, {"MONGODB_URI": "mongodb://stub"}):
            fake_db = mock.MagicMock()
            fake_db.__getitem__.return_value.find_one.return_value = None
            with mock.patch.object(
                sync_workers, "_mongo_db", return_value=fake_db
            ):
                with mock.patch.object(
                    sync_workers,
                    "_claimed",
                    return_value=False,
                ):
                    with mock.patch.object(
                        sync_workers.process_image_translate,
                        "sync",
                        side_effect=lambda *a: sent.append(a[0]),
                    ):
                        result = sync_workers.repair_pages.sync(chapter.pk)

        self.assertEqual(result, {"dispatched": 3})
        self.assertEqual(len(sent), 3)  # três páginas, UMA chamada de task

    def test_live_claim_does_not_spend_a_page_attempt(self):
        from brscans.manhwa.models import Chapter, ImageVariants, Manhwa, Page

        manhwa = Manhwa.objects.create(
            title="m", status="ongoing", description="d"
        )
        chapter = Chapter.objects.create(title="c", slug="c", manhwa=manhwa)
        variant = ImageVariants.objects.create(original="o.webp")
        page = Page.objects.create(chapter=chapter, images=variant)

        with mock.patch.dict(os.environ, {"MONGODB_URI": "mongodb://stub"}):
            with mock.patch.object(
                sync_workers, "_mongo_db", return_value=mock.MagicMock()
            ):
                with mock.patch.object(
                    sync_workers, "_claimed", return_value=True
                ):
                    result = sync_workers.repair_pages.sync(chapter.pk)

        self.assertEqual(result, {"busy": 1})
        page.refresh_from_db()
        self.assertEqual(page.work_attempts, 0)

    def test_missing_mongodb_uri_fails_loudly(self):
        from brscans.manhwa.models import Chapter, Manhwa

        manhwa = Manhwa.objects.create(
            title="m", status="ongoing", description="d"
        )
        chapter = Chapter.objects.create(title="c", slug="c", manhwa=manhwa)
        env = {k: v for k, v in os.environ.items() if k != "MONGODB_URI"}
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "MONGODB_URI"):
                sync_workers.repair_pages.sync(chapter.pk)

    def test_redisparo_nao_toca_capitulo_ja_completo(self):
        """Trabalho já feito pela execução anterior: sai sem baixar nem POSTar."""
        from brscans.manhwa.models import Chapter, ImageVariants, Manhwa, Page

        manhwa = Manhwa.objects.create(
            title="m", status="ongoing", description="d"
        )
        chapter = Chapter.objects.create(title="c", slug="c", manhwa=manhwa)
        variant = ImageVariants.objects.create(
            original="o.webp", translated="t.webp"
        )
        Page.objects.create(chapter=chapter, images=variant)
        Page.objects.create(
            chapter=chapter,
            images=ImageVariants.objects.create(
                original="o2.webp", translated="t2.webp"
            ),
        )

        with mock.patch.object(sync_workers, "_mongo_db") as mongo:
            result = sync_workers.repair_pages.sync(chapter.pk)

        self.assertEqual(result, {"skipped": "nothing to repair"})
        mongo.assert_not_called()
