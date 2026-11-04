"""Reparo manual (count_fix_caps / chapter fix) e download: não podem duplicar
nem quebrar o lote. sqlite em memória; nada toca o banco configurado."""

import os
from unittest import mock

import httpx
from django.test import TestCase, override_settings

from brscans.manhwa.models import Chapter, ImageVariants, Manhwa, Page
from brscans.manhwa.tasks import sync_workers


@override_settings(
    PUBLIC_MEDIA_LOCATION="media/",
    REPAIR_PAGE_WORKERS=1,
    PAGE_MAX_ATTEMPTS=3,
)
class RepairPagesTests(TestCase):
    def setUp(self):
        self.manhwa = Manhwa.objects.create(
            title="m", status="ongoing", description="d"
        )
        self.chapter = Chapter.objects.create(
            title="c", slug="c", manhwa=self.manhwa
        )
        self.pages = []
        for order in range(2):
            variant = ImageVariants.objects.create(original="o.webp")
            self.pages.append(
                Page.objects.create(
                    chapter=self.chapter, images=variant, order=order
                )
            )

    def run_repair(self, **kwargs):
        fake_db = mock.MagicMock()
        fake_db.__getitem__.return_value.find_one.return_value = None
        with mock.patch.dict(os.environ, {"MONGODB_URI": "mongodb://stub"}):
            with mock.patch.object(
                sync_workers, "_mongo_db", return_value=fake_db
            ):
                with mock.patch.object(
                    sync_workers, "_claimed", return_value=False
                ):
                    return sync_workers.repair_pages.sync(
                        self.chapter.pk, **kwargs
                    )

    def test_cron_path_skips_pages_scheduled_by_backoff(self):
        Page.objects.filter(pk=self.pages[0].pk).update(
            work_attempts=3
        )  # desistida
        with mock.patch.object(
            sync_workers, "process_image_translate"
        ) as send:
            send.sync = mock.MagicMock()
            result = self.run_repair()
        self.assertEqual(result, {"dispatched": 1})
        self.assertEqual(send.sync.call_count, 1)

    def test_force_rearms_desisted_and_spends_a_fresh_attempt(self):
        for page in self.pages:
            Page.objects.filter(pk=page.pk).update(
                work_attempts=3, work_next_attempt_at=None
            )
        with mock.patch.object(
            sync_workers, "process_image_translate"
        ) as send:
            send.sync = mock.MagicMock()
            result = self.run_repair(force=True)
        self.assertEqual(result, {"dispatched": 2})
        self.assertEqual(send.sync.call_count, 2)
        for page in self.pages:
            page.refresh_from_db()
            self.assertEqual(page.work_attempts, 1)


@override_settings(
    PUBLIC_MEDIA_LOCATION="media/",
    TRANSLATOR_URL="http://translator-ack",
    FILL_URL="http://fill-ack",
    PAGE_MAX_ATTEMPTS=3,
    PAGE_BACKOFF_MINUTES=30,
)
class FailureRecordingTests(TestCase):
    def setUp(self):
        self.manhwa = Manhwa.objects.create(
            title="m", status="ongoing", description="d"
        )
        self.chapter = Chapter.objects.create(
            title="c", slug="c", manhwa=self.manhwa
        )
        self.variant = ImageVariants.objects.create(original="o.webp")
        self.page = Page.objects.create(
            chapter=self.chapter, images=self.variant
        )

    def test_repair_records_the_reason_and_backs_off(self):
        with mock.patch(
            "brscans.manhwa.tasks.images_variants.generate_presigned_url",
            return_value="http://s3",
        ), mock.patch("httpx.post", side_effect=httpx.ReadTimeout("slow")):
            with mock.patch.dict(os.environ, {"MONGODB_URI": "mongodb://s"}):
                fake_db = mock.MagicMock()
                fake_db.__getitem__.return_value.find_one.return_value = None
                with mock.patch.object(
                    sync_workers, "_mongo_db", return_value=fake_db
                ):
                    with mock.patch.object(
                        sync_workers, "_claimed", return_value=False
                    ):
                        result = sync_workers.repair_pages.sync(
                            self.chapter.pk
                        )
        self.assertEqual(result, {"error": 1})
        self.page.refresh_from_db()
        self.assertEqual(self.page.work_attempts, 1)
        self.assertIn("slow", self.page.work_last_error)
        self.assertIsNotNone(self.page.work_next_attempt_at)

    def test_chapter_fix_queues_the_repair_instead_of_doing_it(self):
        """A rota pública não faz presign nem POST: isso é da task (Gateway 29 s)."""
        from rest_framework.test import APIClient

        with mock.patch(
            "brscans.manhwa.views.chapter.panel_fix_chapter",
            return_value={"task_id": "t1"},
        ) as task, mock.patch("httpx.post") as post:
            response = APIClient().get(f"/chapters/{self.chapter.pk}/fix/")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data, {"status": "queued"})
        task.assert_called_once_with(self.chapter.pk)
        post.assert_not_called()


    def test_legacy_fix_pages_records_and_keeps_the_batch(self):
        from brscans.manhwa.tasks.sync_chapter import fix_pages

        second = ImageVariants.objects.create(original="o2.webp")
        other = Page.objects.create(chapter=self.chapter, images=second, order=1)
        calls = []

        def post(url, **kwargs):
            calls.append(url)
            if len(calls) == 1:
                raise httpx.ReadTimeout("down")
            return httpx.Response(202, json={"accepted": True})

        env = {k: v for k, v in os.environ.items() if k != "MONGODB_URI"}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch(
            "brscans.manhwa.tasks.images_variants.generate_presigned_url",
            return_value="http://s3",
        ), mock.patch("httpx.post", side_effect=post):
            result = fix_pages.sync(self.chapter.pk)

        self.assertEqual(result, {"failed": [self.variant.pk]})
        self.assertIn("down", Page.objects.get(pk=self.page.pk).work_last_error)
        self.assertEqual(Page.objects.get(pk=other.pk).work_attempts, 0)


class DownloadRouteTests(TestCase):
    @override_settings(PUBLIC_MEDIA_LOCATION="media/")
    def test_lambda_dispatch_answers_202_instead_of_500(self):
        from rest_framework.test import APIClient

        with mock.patch(
            "brscans.manhwa.tasks.panel.create_manhwa",
            return_value=object(),  # LambdaAsyncResponse: não é JSON
        ):
            response = APIClient().get(
                "/manhwas/download/", {"link": "http://fonte/cap-1"}
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data, {"status": "queued"})
