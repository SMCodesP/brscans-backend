from datetime import timedelta

from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from brscans.manhwa.models import Chapter, ImageVariants, Manhwa, Page
from brscans.manhwa.work import (
    DONE,
    DESISTED,
    RUNNING,
    begin_chapter_task,
    claim_chapter,
    close_finished,
    due_chapters,
    due_pages,
    pending_counts,
    process_chapter,
    process_page,
)
from brscans.utils.tasks import Saturation


def chapter_with_pages(original=0, translated=0, missing_translated=0):
    """Capítulo com `original` páginas traduzidas, `missing_translated` sem
    tradução e (original=0, translated=0) páginas sem original."""
    manhwa = Manhwa.objects.create(title="m", status="ongoing", description="d")
    chapter = Chapter.objects.create(title="c", slug="c", manhwa=manhwa)
    for _ in range(translated):
        variant = ImageVariants.objects.create(
            original="o.webp", translated="t.webp"
        )
        Page.objects.create(chapter=chapter, images=variant)
    for _ in range(missing_translated):
        variant = ImageVariants.objects.create(original="o.webp")
        Page.objects.create(chapter=chapter, images=variant)
    for _ in range(original):
        variant = ImageVariants.objects.create()
        Page.objects.create(chapter=chapter, images=variant)
    return chapter


@override_settings(
    PUBLIC_MEDIA_LOCATION="media/",
    CHAPTER_WORK_MAX_ATTEMPTS=3,
    CHAPTER_WORK_LEASE_MINUTES=45,
    CHAPTER_WORK_BACKOFF_BASE_MINUTES=30,
)
class ClaimTests(TestCase):
    def test_only_one_claim_wins_while_the_lease_is_alive(self):
        chapter = chapter_with_pages(missing_translated=1)
        self.assertTrue(claim_chapter(chapter.pk))
        self.assertFalse(claim_chapter(chapter.pk))
        chapter.refresh_from_db()
        self.assertEqual(chapter.work_status, RUNNING)
        self.assertEqual(chapter.work_attempts, 1)
        self.assertGreater(chapter.work_locked_until, timezone.now())

    def test_expired_lease_can_be_stolen(self):
        chapter = chapter_with_pages(missing_translated=1)
        self.assertTrue(claim_chapter(chapter.pk))
        Chapter.objects.filter(pk=chapter.pk).update(
            work_locked_until=timezone.now() - timedelta(seconds=1)
        )
        self.assertTrue(claim_chapter(chapter.pk))
        chapter.refresh_from_db()
        self.assertEqual(chapter.work_attempts, 2)

    def test_backoff_blocks_the_claim_until_it_is_due(self):
        chapter = chapter_with_pages(missing_translated=1)
        Chapter.objects.filter(pk=chapter.pk).update(
            work_next_attempt_at=timezone.now() + timedelta(minutes=10)
        )
        self.assertFalse(claim_chapter(chapter.pk))

    def test_force_ignores_backoff_and_rearms_desisted(self):
        chapter = chapter_with_pages(missing_translated=1)
        Chapter.objects.filter(pk=chapter.pk).update(
            work_status=DESISTED,
            work_attempts=9,
            work_next_attempt_at=timezone.now() + timedelta(hours=1),
        )
        self.assertFalse(claim_chapter(chapter.pk))
        self.assertTrue(claim_chapter(chapter.pk, force=True))
        chapter.refresh_from_db()
        self.assertEqual(chapter.work_status, RUNNING)
        self.assertEqual(chapter.work_attempts, 1)

    def test_force_still_respects_a_live_lease(self):
        chapter = chapter_with_pages(missing_translated=1)
        self.assertTrue(claim_chapter(chapter.pk))
        self.assertFalse(claim_chapter(chapter.pk, force=True))

    @override_settings(CHAPTER_QUEUE_LEASE_MINUTES=360)
    def test_dispatch_lease_covers_the_modal_queue(self):
        """A fila do Modal pode passar de 45 min; o cron não pode redisparar."""
        chapter = chapter_with_pages(missing_translated=1)
        self.assertTrue(claim_chapter(chapter.pk))
        chapter.refresh_from_db()
        self.assertGreater(
            chapter.work_locked_until,
            timezone.now() + timedelta(minutes=359),
        )

    @override_settings(CHAPTER_QUEUE_LEASE_MINUTES=360)
    def test_beginning_the_task_shrinks_the_lease_back(self):
        chapter = chapter_with_pages(missing_translated=1)
        self.assertTrue(claim_chapter(chapter.pk))
        begin_chapter_task(chapter.pk)
        chapter.refresh_from_db()
        self.assertLess(
            chapter.work_locked_until,
            timezone.now() + timedelta(minutes=46),
        )
        self.assertGreater(chapter.work_locked_until, timezone.now())


@override_settings(
    PUBLIC_MEDIA_LOCATION="media/",
    CHAPTER_WORK_MAX_ATTEMPTS=3,
    CHAPTER_WORK_LEASE_MINUTES=45,
    CHAPTER_WORK_BACKOFF_BASE_MINUTES=30,
)
class RepairTests(TestCase):
    def test_counts_only_pages_that_need_work(self):
        chapter = chapter_with_pages(
            original=1, translated=2, missing_translated=3
        )
        self.assertEqual(pending_counts(chapter.pk), (1, 3, 6))

    def test_done_when_nothing_is_pending(self):
        chapter = chapter_with_pages(translated=2)
        calls = []
        self.assertEqual(
            process_chapter(chapter, lambda c, s: calls.append(c.pk)), DONE
        )
        self.assertEqual(calls, [])
        chapter.refresh_from_db()
        self.assertEqual(chapter.work_status, DONE)
        self.assertIsNone(chapter.work_locked_until)

    def test_dispatch_failure_releases_with_backoff_and_error(self):
        chapter = chapter_with_pages(missing_translated=2)

        def boom(ch, needs_sync):
            raise RuntimeError("modal fora")

        self.assertEqual(process_chapter(chapter, boom), "error")
        chapter.refresh_from_db()
        self.assertEqual(chapter.work_status, RUNNING)
        self.assertIsNone(chapter.work_locked_until)
        self.assertIn("modal fora", chapter.work_last_error)
        self.assertGreater(chapter.work_next_attempt_at, timezone.now())
        self.assertEqual(chapter.work_attempts, 1)

    def test_dispatched_records_pending_for_the_next_run(self):
        chapter = chapter_with_pages(missing_translated=2)
        self.assertEqual(
            process_chapter(chapter, lambda ch, needs_sync: None), "dispatched"
        )
        chapter.refresh_from_db()
        self.assertEqual(chapter.work_missing_pages, 2)
        # A trava ainda vale: a próxima execução não recomeça o capítulo.
        self.assertFalse(claim_chapter(chapter.pk))

    def test_desists_after_max_attempts_without_progress(self):
        chapter = chapter_with_pages(missing_translated=5)
        errors = iter(["timeout no Modal", "tradução vazia", "HTTP 500"])
        dispatched = []

        def failing(ch, needs_sync):
            dispatched.append(ch.pk)
            raise RuntimeError(next(errors))

        Chapter.objects.filter(pk=chapter.pk).update(work_attempts=2)
        outcome = process_chapter(chapter, failing)
        self.assertEqual(outcome, "error")

        # A próxima tentativa é a terceira: sem progresso, desiste sem disparar.
        Chapter.objects.filter(pk=chapter.pk).update(
            work_locked_until=None, work_next_attempt_at=None
        )
        self.assertEqual(process_chapter(chapter, failing), "desisted")
        self.assertEqual(len(dispatched), 1)
        chapter.refresh_from_db()
        self.assertEqual(chapter.work_status, DESISTED)
        self.assertIn("3 tentativas", chapter.work_last_error)
        self.assertIn("timeout no Modal", chapter.work_last_error)

    def test_progress_credits_back_one_attempt(self):
        chapter = chapter_with_pages(missing_translated=5)
        Chapter.objects.filter(pk=chapter.pk).update(
            work_attempts=3, work_missing_pages=9, work_locked_until=None
        )
        self.assertEqual(
            process_chapter(chapter, lambda ch, needs_sync: None), "dispatched"
        )
        chapter.refresh_from_db()
        # 3 - 1 (progresso) + 1 (esta tentativa): progresso adia a desistência
        # sem nunca zerar, então um capítulo que some 1 página por vez não é
        # desistido e um erro permanente ainda desiste em poucas tentativas.
        self.assertEqual(chapter.work_attempts, 3)

    def test_progress_never_makes_a_permanent_error_loop(self):
        chapter = chapter_with_pages(missing_translated=5)
        Chapter.objects.filter(pk=chapter.pk).update(
            work_attempts=3, work_missing_pages=9, work_locked_until=None
        )

        def boom(ch, needs_sync):
            raise RuntimeError("fonte fora")

        self.assertEqual(process_chapter(chapter, boom), "error")
        chapter.refresh_from_db()
        self.assertEqual(chapter.work_attempts, 3)
        Chapter.objects.filter(pk=chapter.pk).update(
            work_locked_until=None, work_next_attempt_at=None
        )
        self.assertEqual(process_chapter(chapter, boom), "desisted")

    def test_saturation_returns_the_attempt_and_backs_off_long(self):
        """429 do Modal não é falha do capítulo: devolve a tentativa e espera."""
        chapter = chapter_with_pages(missing_translated=2)
        Chapter.objects.filter(pk=chapter.pk).update(work_attempts=2)

        def saturated(ch, needs_sync):
            raise Saturation("http://ack respondeu 429")

        self.assertEqual(process_chapter(chapter, saturated), "deferred")
        chapter.refresh_from_db()
        self.assertEqual(chapter.work_attempts, 2)  # não queimou a 3ª
        self.assertEqual(chapter.work_status, RUNNING)
        self.assertIsNone(chapter.work_locked_until)
        self.assertIn("429", chapter.work_last_error)
        self.assertLessEqual(
            chapter.work_next_attempt_at,
            timezone.now() + timedelta(minutes=10),
        )

    def test_empty_running_chapter_only_waits_for_its_lock(self):
        """Merge vivo tem trava; sem trava, o capítulo vazio volta para a fila."""
        manhwa = Manhwa.objects.create(
            title="m", status="ongoing", description="d"
        )
        merging = Chapter.objects.create(
            title="c", slug="c", manhwa=manhwa, work_status=RUNNING
        )
        Chapter.objects.filter(pk=merging.pk).update(
            work_locked_until=timezone.now() + timedelta(minutes=10)
        )
        self.assertNotIn(merging.pk, [c.pk for c in due_chapters()])
        Chapter.objects.filter(pk=merging.pk).update(
            work_locked_until=timezone.now() - timedelta(minutes=1)
        )
        self.assertIn(merging.pk, [c.pk for c in due_chapters()])

    def test_locked_chapter_is_not_dispatched(self):
        chapter = chapter_with_pages(missing_translated=1)
        Chapter.objects.filter(pk=chapter.pk).update(
            work_status=RUNNING,
            work_locked_until=timezone.now() + timedelta(minutes=10),
        )
        calls = []
        self.assertEqual(
            process_chapter(chapter, lambda c, s: calls.append(c.pk)), "locked"
        )
        self.assertEqual(calls, [])

    def test_chapter_without_pages_is_due_for_sync(self):
        manhwa = Manhwa.objects.create(
            title="m", status="ongoing", description="d"
        )
        empty = Chapter.objects.create(title="c", slug="c", manhwa=manhwa)
        due = [c.pk for c in due_chapters()]
        self.assertIn(empty.pk, due)
        calls = []
        self.assertEqual(
            process_chapter(
                empty, lambda c, needs_sync: calls.append(needs_sync)
            ),
            "dispatched",
        )
        self.assertEqual(calls, [True])  # sem página: precisa buscar na fonte

    def test_close_finished_marks_translated_chapters_done(self):
        finished = chapter_with_pages(translated=2)
        pending = chapter_with_pages(missing_translated=1)
        Chapter.objects.filter(pk__in=[finished.pk, pending.pk]).update(
            work_status=RUNNING, work_attempts=2
        )
        self.assertEqual(close_finished(), 1)
        finished.refresh_from_db()
        pending.refresh_from_db()
        self.assertEqual(finished.work_status, DONE)
        self.assertEqual(finished.work_attempts, 0)
        self.assertEqual(pending.work_status, RUNNING)

    def test_due_chapters_skips_locked_and_scheduled(self):
        ready = chapter_with_pages(missing_translated=1)
        locked = chapter_with_pages(missing_translated=1)
        later = chapter_with_pages(missing_translated=1)
        Chapter.objects.filter(pk=locked.pk).update(
            work_locked_until=timezone.now() + timedelta(minutes=10)
        )
        Chapter.objects.filter(pk=later.pk).update(
            work_next_attempt_at=timezone.now() + timedelta(minutes=10)
        )
        self.assertEqual(
            [c.pk for c in due_chapters()],
            [ready.pk],
        )

    def test_due_chapters_returns_one_row_per_chapter(self):
        """Uma linha por página comeria o orçamento do reparo com o mesmo capítulo."""
        chapter = chapter_with_pages(
            translated=1, missing_translated=4
        )
        empty = chapter_with_pages()
        self.assertEqual(
            [c.pk for c in due_chapters()], [empty.pk, chapter.pk]
        )


@override_settings(
    PUBLIC_MEDIA_LOCATION="media/",
    PAGE_MAX_ATTEMPTS=3,
    PAGE_LEASE_MINUTES=20,
)
class PageRepairTests(TestCase):
    def page_with(self, translated=False):
        chapter = chapter_with_pages()
        variant = ImageVariants.objects.create(
            original="o.webp",
            translated="t.webp" if translated else None,
        )
        return Page.objects.create(chapter=chapter, images=variant)

    def test_desisted_page_does_not_block_the_others(self):
        stuck = self.page_with()
        stuck_next = self.page_with()
        Page.objects.filter(pk=stuck.pk).update(work_attempts=3)
        Page.objects.filter(pk=stuck_next.pk).update(work_attempts=2)
        calls = []
        self.assertEqual(
            process_page(
                Page.objects.get(pk=stuck.pk),
                lambda p, v, ok: calls.append(p.pk),
            ),
            "desisted",
        )
        self.assertEqual(
            process_page(
                Page.objects.get(pk=stuck_next.pk),
                lambda p, v, ok: calls.append(p.pk),
            ),
            "dispatched",
        )
        self.assertEqual(calls, [stuck_next.pk])

    def test_translated_marks_done_and_resets_attempts(self):
        page = self.page_with(translated=True)
        Page.objects.filter(pk=page.pk).update(work_attempts=2)
        self.assertEqual(process_page(page, lambda p, v, ok: None), "done")
        page.refresh_from_db()
        self.assertEqual(page.work_attempts, 0)

    def test_lease_prevents_double_send(self):
        page = self.page_with()
        self.assertEqual(
            process_page(page, lambda p, v, ok: None), "dispatched"
        )
        Page.objects.filter(pk=page.pk).update(
            work_next_attempt_at=timezone.now() + timedelta(minutes=10)
        )
        self.assertEqual(
            process_page(Page.objects.get(pk=page.pk), lambda p, v, ok: None),
            "locked",
        )

    def test_failure_records_error_and_backs_off(self):
        page = self.page_with()

        def boom(p, v, ok):
            raise RuntimeError("modal saturado")

        self.assertEqual(process_page(page, boom), "error")
        page.refresh_from_db()
        self.assertEqual(page.work_attempts, 1)
        self.assertIn("modal saturado", page.work_last_error)
        self.assertGreater(page.work_next_attempt_at, timezone.now())

    def test_saturation_does_not_exhaust_the_page(self):
        """Página no último crédito + 429: não desiste, só espera."""
        page = self.page_with()
        Page.objects.filter(pk=page.pk).update(work_attempts=2)

        def saturated(p, v, ok):
            raise Saturation("http://ack respondeu 429")

        self.assertEqual(
            process_page(Page.objects.get(pk=page.pk), saturated), "deferred"
        )
        page.refresh_from_db()
        self.assertEqual(page.work_attempts, 2)
        self.assertIn("429", page.work_last_error)
        self.assertIsNotNone(page.work_next_attempt_at)
        # Volta sozinha depois do backoff, sem ter desistido.
        self.assertEqual(
            Page.objects.filter(pk=page.pk, work_attempts__lt=3).count(), 1
        )

    def test_third_failure_exhausts_the_page_silently(self):
        page = self.page_with()
        Page.objects.filter(pk=page.pk).update(work_attempts=2)

        def boom(p, v, ok):
            raise RuntimeError("permanente")

        self.assertEqual(
            process_page(Page.objects.get(pk=page.pk), boom), "error"
        )
        page.refresh_from_db()
        self.assertEqual(page.work_attempts, 3)
        self.assertIsNone(page.work_next_attempt_at)

    def test_due_pages_skips_desisted_and_scheduled(self):
        ready = self.page_with()
        later = self.page_with()
        exhausted = self.page_with()
        Page.objects.filter(pk=later.pk).update(
            work_next_attempt_at=timezone.now() + timedelta(minutes=10)
        )
        Page.objects.filter(pk=exhausted.pk).update(work_attempts=3)
        self.assertEqual(
            [p.pk for p in due_pages(ready.chapter_id)], [ready.pk]
        )


class SourceFixesTests(TestCase):
    def test_comizy_cdn_uses_site_referer(self):
        from brscans.utils.image import get_referer_from_url

        self.assertEqual(
            get_referer_from_url("https://x3.cmzcdn.org/e/a.webp"),
            "https://comizy.io/",
        )

    def test_due_chapters_prioritize_newest(self):
        from brscans.manhwa.models import Chapter
        from brscans.manhwa.work import due_chapters

        old = Chapter.objects.create(title="old", slug="old")
        new = Chapter.objects.create(title="new", slug="new")
        self.assertEqual(
            [chapter.pk for chapter in due_chapters()], [new.pk, old.pk]
        )

    def test_missing_originals_scrape_only_dispatches(self):
        """A parte scrape lê a fonte e manda o download ao Modal."""
        from brscans.manhwa.tasks import sync_chapter as module

        chapter = chapter_with_pages(translated=2)
        source = mock.Mock()
        source.chapter.return_value = {"pages": ["a", "b", "c"]}
        with (
            mock.patch.object(module, "get_source_by_link", return_value=source),
            mock.patch.object(module, "apply_missing_originals") as apply,
        ):
            module.sync_missing_original_pages.sync(
                chapter.pk, chapter.manhwa_id
            )
        apply.assert_called_once_with(
            chapter.pk, chapter.manhwa_id, ["a", "b", "c"]
        )
        self.assertEqual(chapter.pages.count(), 2)

    def test_partial_download_keeps_existing_pages(self):
        from brscans.manhwa.tasks import sync_chapter as module

        chapter = chapter_with_pages(translated=2)
        with mock.patch.object(
            module, "merge_page_groups", side_effect=RuntimeError("fonte caiu")
        ), mock.patch.object(module, "download_images", return_value=[object()]):
            result = module.apply_missing_originals.sync(
                chapter.pk, chapter.manhwa_id, ["a", "b", "c"]
            )
        self.assertIn("error", result)
        self.assertEqual(chapter.pages.count(), 2)
