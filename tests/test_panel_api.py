"""Testes das rotas do painel (/panel) e da edição de URLs.

Rodam com sqlite em memória (settings.TESTING); nada toca o banco configurado.
"""

from unittest import mock

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from brscans.manhwa.models import Chapter, ImageVariants, Manhwa, Page

MEDIA_ROOT = "/tmp/brscans-tests-media"


@override_settings(MEDIA_ROOT=MEDIA_ROOT, MEDIA_URL="/media/")
class PanelTestBase(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            "staff", password="x", is_staff=True
        )
        self.user = User.objects.create_user("normal", password="x")
        self.manhwa = Manhwa.objects.create(title="Teste", status="ongoing")
        self.chapter = Chapter.objects.create(
            title="Cap 1", slug="cap-1", manhwa=self.manhwa
        )

    def client_for(self, user):
        client = APIClient()
        token, _ = Token.objects.get_or_create(user=user)
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return client

    def page_with(self, original=True, translated=True, order=0):
        images = ImageVariants.objects.create()
        if original:
            images.original.save("page.webp", ContentFile(b"x"), save=True)
        if translated:
            images.translated.save("page-t.webp", ContentFile(b"x"), save=True)
        return Page.objects.create(
            chapter=self.chapter, images=images, order=order
        )


class TestPanelAuth(PanelTestBase):
    def test_anonymous_gets_401(self):
        response = APIClient().get("/panel/manhwas/")
        self.assertEqual(response.status_code, 401)

    def test_normal_user_gets_403(self):
        response = self.client_for(self.user).get("/panel/manhwas/")
        self.assertEqual(response.status_code, 403)

    def test_staff_gets_200(self):
        response = self.client_for(self.staff).get("/panel/manhwas/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)


class TestPanelManhwa(PanelTestBase):
    def test_list_exposes_source_status_and_counts(self):
        self.manhwa.source_status = "blocked"
        self.manhwa.save()
        self.page_with()
        response = self.client_for(self.staff).get("/panel/manhwas/")
        row = response.data["results"][0]
        self.assertEqual(row["source_status"], "blocked")
        self.assertEqual(row["chapters_count"], 1)
        self.assertEqual(row["problem_pages"], 0)

    def test_filter_source_status_never_is_null(self):
        client = self.client_for(self.staff)
        never = Manhwa.objects.create(title="Nunca checado", status="ongoing")
        self.manhwa.source_status = "blocked"
        self.manhwa.save()
        response = client.get("/panel/manhwas/?source_status=never")
        self.assertEqual(
            [row["id"] for row in response.data["results"]], [never.pk]
        )

    def test_create_requires_url(self):
        response = self.client_for(self.staff).post("/panel/manhwas/", {})
        self.assertEqual(response.status_code, 400)
        self.assertIn("link", response.data)

    def test_create_queues_task(self):
        client = self.client_for(self.staff)
        with mock.patch("brscans.manhwa.views.panel.create_manhwa") as task:
            task.return_value = {"task_id": "abc", "status": "queued"}
            response = client.post(
                "/panel/manhwas/", {"link": "https://example.com/manga/x/"}
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data, {"task": "abc", "status": "queued"})
        task.assert_called_once()

    def test_sync_and_check_source_are_post(self):
        client = self.client_for(self.staff)
        self.assertEqual(
            client.get(f"/panel/manhwas/{self.manhwa.pk}/sync/").status_code,
            405,
        )
        with mock.patch("brscans.manhwa.views.panel.panel_sync_manhwa") as sync:
            sync.return_value = {"task_id": "t1"}
            response = client.post(f"/panel/manhwas/{self.manhwa.pk}/sync/")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["task"], "t1")


class TestPanelChaptersAndProblems(PanelTestBase):
    def test_chapter_counts(self):
        self.page_with(translated=True)
        self.page_with(translated=False, order=1)
        response = self.client_for(self.staff).get(
            f"/panel/manhwas/{self.manhwa.pk}/chapters/"
        )
        row = response.data["results"][0]
        self.assertEqual(row["pages_count"], 2)
        self.assertEqual(row["translated_count"], 1)
        self.assertEqual(row["problem_pages"], 1)

    def test_problems_lists_only_broken_chapters(self):
        self.page_with()
        self.assertEqual(
            self.client_for(self.staff).get("/panel/problems/").data["count"], 0
        )
        self.page_with(translated=False, order=1)
        response = self.client_for(self.staff).get("/panel/problems/")
        self.assertEqual(response.data["count"], 1)
        row = response.data["results"][0]
        self.assertEqual(row["manhwa"]["id"], self.manhwa.pk)
        self.assertEqual(row["reason"], "sem_traducao")

    def test_problem_pages_filters_by_chapter(self):
        broken = self.page_with(translated=False)
        self.page_with()
        response = self.client_for(self.staff).get("/panel/problems/pages/")
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], broken.pk)
        self.assertEqual(response.data["results"][0]["reason"], "sem_traducao")

    def test_chapter_pages_exposes_paths(self):
        page = self.page_with(translated=False)
        response = self.client_for(self.staff).get(
            f"/panel/chapters/{self.chapter.pk}/pages/"
        )
        row = response.data["results"][0]
        self.assertEqual(row["id"], page.pk)
        self.assertEqual(row["reason"], "sem_traducao")
        self.assertTrue(row["images"]["original_path"])
        self.assertIsNone(row["images"]["translated_path"])


@override_settings(MEDIA_ROOT=MEDIA_ROOT, MEDIA_URL="/media/")
class TestVariantEditing(PanelTestBase):
    def setUp(self):
        super().setUp()
        self.page = self.page_with(translated=False)
        self.images = self.page.images
        self.url = f"/images/{self.images.pk}/"

    def test_anonymous_cannot_write_but_can_read(self):
        client = APIClient()
        self.assertEqual(client.get(self.url).status_code, 200)
        self.assertEqual(
            client.patch(
                self.url, {"translated": "x.webp"}, format="json"
            ).status_code,
            401,
        )

    def test_normal_user_cannot_write(self):
        response = self.client_for(self.user).patch(
            self.url, {"translated": self.images.original.name}, format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_unknown_file_is_rejected(self):
        response = self.client_for(self.staff).patch(
            self.url, {"translated": "chapters/999/nada.webp"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("translated", response.data)

    def test_outside_url_is_rejected(self):
        response = self.client_for(self.staff).patch(
            self.url,
            {"translated": "https://evil.example.com/x.webp"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_path_edit_keeps_previous_and_marks_manual(self):
        original = self.images.original.name
        response = self.client_for(self.staff).patch(
            self.url, {"translated": original}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.images.refresh_from_db()
        self.assertEqual(self.images.translated.name, original)
        self.assertTrue(self.images.manual_translated)

        other = self.page_with(order=5).images
        previous = other.translated.name  # o storage pode renomear
        response = self.client_for(self.staff).patch(
            f"/images/{other.pk}/", {"translated": original}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        other.refresh_from_db()
        self.assertEqual(other.previous_translated, previous)

    def test_pipeline_patch_is_not_manual(self):
        bot = User.objects.create_user("translator", password="x", is_staff=True)
        response = self.client_for(bot).patch(
            self.url, {"translated": self.images.original.name}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.images.refresh_from_db()
        self.assertFalse(self.images.manual_translated)

    def test_use_original_endpoint(self):
        original = self.images.original.name
        response = self.client_for(self.staff).post(f"{self.url}use-original/")
        self.assertEqual(response.status_code, 200)
        self.images.refresh_from_db()
        self.assertEqual(self.images.translated.name, original)
        self.assertTrue(self.images.manual_translated)
        self.assertTrue(self.images.original)  # não perdeu o original

    def test_absolute_media_url_is_normalized(self):
        original = self.images.original.name
        response = self.client_for(self.staff).patch(
            self.url, {"translated": f"/media/{original}"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.images.refresh_from_db()
        self.assertEqual(self.images.translated.name, original)


class TestPanelFixChapter(PanelTestBase):
    """O botão Consertar não pode apagar página boa nem edição manual."""

    def test_preserves_pages_and_manual_translation(self):
        from brscans.manhwa.tasks import panel as panel_tasks

        good = self.page_with(order=0)
        manual = self.page_with(translated=False, order=1)
        manual.images.translated = manual.images.original.name
        manual.images.manual_translated = True
        manual.images.save()
        broken = self.page_with(original=False, translated=False, order=2)
        self.chapter.source = "https://example.com/cap/1/"
        self.chapter.save()

        source = mock.Mock()
        source.chapter.return_value = {"pages": ["u1", "u2", "u3"]}
        get_source = mock.patch.object(
            panel_tasks.sources, "get_source_by_link", return_value=source
        )
        add_original = mock.patch(
            "brscans.manhwa.tasks.sync_chapter.add_original_to_page"
        )
        with get_source, add_original as add:
            result = panel_tasks.panel_fix_chapter.sync(self.chapter.pk)

        for page in (good, manual, broken):
            self.assertTrue(Page.objects.filter(pk=page.pk).exists())
        manual.images.refresh_from_db()
        self.assertEqual(
            manual.images.translated.name, manual.images.original.name
        )
        self.assertEqual(result["manual"], [manual.pk])
        self.assertEqual(result["refetched"], [broken.pk])
        add.assert_called_once_with(
            broken.images.pk,
            ["u3"],
            ["chapters", str(self.chapter.pk)],
            self.manhwa.pk,
        )
        source.chapter.assert_called_once()

    def test_refuses_when_page_has_no_variant(self):
        from brscans.manhwa.tasks import panel as panel_tasks

        Page.objects.create(chapter=self.chapter, images=None, order=0)
        result = panel_tasks.panel_fix_chapter.sync(self.chapter.pk)
        self.assertIn("error", result)


class TestMeEndpoint(PanelTestBase):
    def test_me_reports_is_staff(self):
        response = self.client_for(self.staff).get("/auth/me/")
        self.assertTrue(response.data["is_staff"])
        response = self.client_for(self.user).get("/auth/me/")
        self.assertFalse(response.data["is_staff"])


class TestFixButtonQueuesTheWork(PanelTestBase):
    """O botão não faz presign nem POST no thread da API (Gateway corta em 29 s)."""

    def test_fix_returns_202_without_touching_the_modal(self):
        self.page_with(translated=False)
        with mock.patch(
            "brscans.manhwa.views.panel.panel_fix_chapter",
            return_value={"task_id": "t1"},
        ) as task, mock.patch(
            "brscans.manhwa.tasks.images_variants._post_ack"
        ) as post:
            response = self.client_for(self.staff).post(
                f"/panel/chapters/{self.chapter.pk}/fix/"
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data, {"task": "t1", "status": "queued"})
        task.assert_called_once_with(self.chapter.pk)
        post.assert_not_called()
