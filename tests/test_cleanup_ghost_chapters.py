"""Testes do varredor de órfãos de mídia (cleanup_ghost_chapters).

Usa um S3 falso em memória: nenhum teste toca a AWS.
"""

from datetime import datetime, timedelta, timezone
from io import StringIO
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from brscans.manhwa.management.commands import cleanup_ghost_chapters
from brscans.manhwa.models import ImageVariants

OLD = datetime.now(timezone.utc) - timedelta(days=10)


def obj(key, size=10, etag='"e"', when=OLD):
    return {
        "Key": key,
        "Size": size,
        "ETag": etag,
        "LastModified": when,
    }


class ClientError(Exception):
    pass


class FakeS3:
    """Só o que o command usa: paginator (com Delimiter), delete e head."""

    exceptions = mock.Mock(ClientError=ClientError)

    def __init__(self, objects):
        self.objects = {o["Key"]: o for o in objects}
        self.deleted = []
        self.headed = []

    def get_paginator(self, name):
        assert name == "list_objects_v2"

        class Paginator:
            def paginate(inner, Bucket, Prefix, Delimiter=None):
                hits = [
                    o for k, o in self.objects.items() if k.startswith(Prefix)
                ]
                if Delimiter:
                    prefixes = {
                        Prefix
                        + k[len(Prefix) :].split(Delimiter)[0]
                        + Delimiter
                        for k in (o["Key"] for o in hits)
                        if Delimiter in k[len(Prefix) :]
                    }
                    return [
                        {
                            "CommonPrefixes": [{"Prefix": p} for p in prefixes],
                            "Contents": [],
                        }
                    ]
                return [{"Contents": hits}]

        return Paginator()

    def delete_objects(self, Bucket, Delete):
        for item in Delete["Objects"]:
            self.deleted.append(item["Key"])
            self.objects.pop(item["Key"], None)
        return {"Deleted": Delete["Objects"]}

    def head_object(self, Bucket, Key):
        self.headed.append(Key)
        if Key not in self.objects:
            raise ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject"
            )
        return {
            "ETag": self.objects[Key]["ETag"],
            "ContentLength": self.objects[Key]["Size"],
        }


@override_settings(AWS_STORAGE_BUCKET_NAME="bucket-teste")
class CleanupTest(TestCase):
    def setUp(self):
        patcher = mock.patch.object(cleanup_ghost_chapters, "s3_client")
        self.client_mock = patcher.start()
        self.addCleanup(patcher.stop)

        self.variant = ImageVariants.objects.create(
            original="chapters/1/keep.webp",
            translated="chapters/1/translated/keep.jpeg",
            previous_translated="chapters/1/translated/anteriores/keep-old.jpeg",
        )

    def run_with(self, objects):
        fake = FakeS3(objects)
        self.client_mock.get_paginator = fake.get_paginator
        self.client_mock.delete_objects = fake.delete_objects
        self.client_mock.head_object = fake.head_object
        self.client_mock.exceptions = FakeS3.exceptions
        return fake

    def call(self, *args):
        out = StringIO()
        call_command("cleanup_ghost_chapters", *args, stdout=out)
        return out.getvalue()

    def test_keeps_every_referenced_column(self):
        fake = self.run_with(
            [
                obj("media/chapters/1/raw/orfao.jpeg"),
                obj("media/chapters/1/translated/anteriores/keep-old.jpeg"),
                obj("media/chapters/1/translated/keep.jpeg"),
                obj("media/chapters/1/keep.webp"),
            ]
        )
        self.call()
        self.assertEqual(fake.deleted, [])

    def test_deletes_orphan_of_deleted_chapter(self):
        fake = self.run_with(
            [
                obj("media/chapters/99/raw/orfao.jpeg"),
                obj("media/chapters/1/keep.webp"),
            ]
        )
        self.call("--delete")
        self.assertEqual(fake.deleted, ["media/chapters/99/raw/orfao.jpeg"])

    def test_dry_run_is_default(self):
        fake = self.run_with([obj("media/chapters/99/raw/orfao.jpeg")])
        out = self.call()
        self.assertEqual(fake.deleted, [])
        self.assertIn("Dry-run", out)

    def test_skips_young_objects(self):
        fake = self.run_with(
            [
                obj(
                    "media/chapters/99/raw/novo.jpeg",
                    when=datetime.now(timezone.utc),
                )
            ]
        )
        self.call("--delete")
        self.assertEqual(fake.deleted, [])

    def test_never_touches_static_or_bucket_root(self):
        fake = self.run_with(
            [
                obj("static/admin/css/base.css"),
                obj("lc/video.mp4"),
                obj("media/chapters/1/keep.webp"),
            ]
        )
        self.call("--delete")
        self.assertEqual(fake.deleted, [])

    def test_stops_at_deadline_and_leaves_the_rest(self):
        fake = self.run_with(
            [
                obj(f"media/chapters/99/raw/{i}.jpeg")
                for i in range(1500)  # dois lotes de 1000
            ]
        )
        with mock.patch.object(
            cleanup_ghost_chapters.time, "monotonic"
        ) as clock:
            clock.side_effect = [0, 0, 10_000]  # 1ª lote ok, 2ª estourou
            out = self.call("--delete")
        self.assertIn("próxima rodada", out)
        self.assertEqual(len(fake.deleted), 1000)

    def test_heads_only_candidates(self):
        fake = self.run_with(
            [
                obj("media/chapters/1/keep.webp"),
                obj("media/chapters/99/raw/orfao.jpeg"),
            ]
        )
        self.call("--delete")
        self.assertEqual(fake.headed, ["media/chapters/99/raw/orfao.jpeg"])

    def test_skips_object_that_changed_after_listing(self):
        fake = self.run_with([obj("media/chapters/99/raw/orfao.jpeg")])
        # o command usa o head_object do cliente; aqui ele vê outro ETag
        self.client_mock.head_object = mock.Mock(
            return_value={"ETag": '"novo"', "ContentLength": 10}
        )
        self.call("--delete")
        self.assertEqual(fake.deleted, [])

    def test_refuses_without_s3(self):
        with mock.patch.object(cleanup_ghost_chapters, "s3_client", None):
            with self.assertRaises(CommandError):
                self.call()

    def test_refuses_without_bucket(self):
        with override_settings(AWS_STORAGE_BUCKET_NAME=""):
            fake = self.run_with([obj("media/chapters/99/raw/orfao.jpeg")])
            with self.assertRaises(CommandError):
                self.call("--delete")
            self.assertEqual(fake.deleted, [])
