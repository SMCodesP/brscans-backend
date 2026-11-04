"""
Management command to find and delete S3 media that no database row references.

Usage:
    # Dry-run (default): lists what would be deleted.
    python manage.py cleanup_ghost_chapters

    # Actually delete:
    python manage.py cleanup_ghost_chapters --delete

Run it from a daily cron/EventBridge job. In a Lambda deployment schedule it
with `zappa manage ...` or a regular management-command schedule.

Safety rules (all of them are why this lives in one place):
  - the bucket comes from settings (AWS_STORAGE_BUCKET_NAME); an empty name
    aborts the run instead of sweeping nothing and reporting a clean bucket;
  - only objects under `media/` are considered; `static/` and the bucket root
    are never touched;
  - an object is kept if any ImageVariants column references its path. Besides
    the image fields, the panel's `previous_translated` (history) counts. That
    is the only table with a file field in the schema; UserProfile.avatar is a
    Discord URL and the panel only edits into ImageVariants;
  - the object must be older than --min-age-days (default 2), so a worker that
    just uploaded a file has time to record it in the database;
  - only candidates for deletion are HEADed, right before deleting, and
    skipped if their ETag or size changed since they were listed;
  - deletion stops at DELETE_MINUTES so it fits the Lambda timeout; whatever
    is left is deleted by the next run.
"""

import time
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from brscans.manhwa.models import ImageVariants
from brscans.services.s3 import s3_client

MEDIA_PREFIX = "media/"
DELETE_MINUTES = 12  # margem para o timeout de 15 min da Lambda

# ImageField/CharField columns that hold a storage path. Listed explicitly
# because a new field must be added here before its files become deletable.
PATH_FIELDS = (
    "minimum",
    "medium",
    "original",
    "translated",
    "raw",
    "upscaled",
    "previous_translated",
)


def list_media(bucket_name):
    """Every object under media/, so static/ and the bucket root are never
    listed."""
    out = []
    for page in s3_client.get_paginator("list_objects_v2").paginate(
        Bucket=bucket_name, Prefix=MEDIA_PREFIX
    ):
        for obj in page.get("Contents", []):
            out.append(
                {
                    "key": obj["Key"],
                    "size": obj["Size"],
                    "etag": obj["ETag"],
                    "last_modified": obj["LastModified"],
                }
            )
    return out


class Command(BaseCommand):
    help = (
        "Find and delete media objects in S3 that no database row references."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Actually delete orphan objects. Without it, only lists them.",
        )
        parser.add_argument(
            "--min-age-days",
            type=int,
            default=2,
            help="Skip objects modified in the last N days (default: 2).",
        )

    def handle(self, *args, **options):
        if not s3_client:
            raise CommandError("S3 não configurado (USE_S3=False).")
        bucket_name = getattr(settings, "AWS_STORAGE_BUCKET_NAME", "")
        if not bucket_name:
            raise CommandError(
                "AWS_STORAGE_BUCKET_NAME/S3_STATIC_BUCKET vazio: "
                "nada foi varrido."
            )
        deadline = time.monotonic() + DELETE_MINUTES * 60

        refs = self.referenced_paths()
        objects = list_media(bucket_name)
        self.stdout.write(
            f"  {len(objects)} objetos encontrados em {MEDIA_PREFIX}"
        )

        cutoff = datetime.now(timezone.utc) - timedelta(
            days=options["min_age_days"]
        )
        orphans = [
            o
            for o in objects
            if self.to_path(o["key"]) not in refs
            and o["last_modified"].replace(tzinfo=timezone.utc) < cutoff
        ]
        size = sum(o["size"] for o in orphans)
        self.stdout.write(
            self.style.WARNING(
                f"  Órfãos (sem referência, com mais de "
                f"{options['min_age_days']} dias): {len(orphans)} "
                f"({size / 1e9:.3f} GB)"
            )
        )

        if not orphans:
            return

        if not options["delete"]:
            for o in orphans[:20]:
                self.stdout.write(f"    {o['key']}")
            self.stdout.write(
                self.style.NOTICE(
                    "\n  Dry-run. Rode com --delete para remover."
                )
            )
            return

        deleted = 0
        for chunk in range(0, len(orphans), 1000):
            if time.monotonic() > deadline:
                self.stdout.write(
                    self.style.WARNING(
                        f"\n  Tempo esgotado: {len(orphans) - deleted} "
                        "objetos ficam para a próxima rodada."
                    )
                )
                break
            batch = self.unchanged(bucket_name, orphans[chunk : chunk + 1000])
            if not batch:
                continue
            keys = [o["key"] for o in batch]
            s3_client.delete_objects(
                Bucket=bucket_name,
                Delete={"Objects": [{"Key": k} for k in keys]},
            )
            deleted += len(keys)
            self.stdout.write(f"    {deleted}/{len(orphans)} apagados")

        self.stdout.write(
            self.style.SUCCESS(f"\n  Pronto: {deleted} objetos apagados.")
        )

    @staticmethod
    def unchanged(bucket_name, batch):
        """Candidates whose ETag and size still match the listing."""
        kept = []
        for obj in batch:
            try:
                h = s3_client.head_object(Bucket=bucket_name, Key=obj["key"])
            except s3_client.exceptions.ClientError as exc:
                if exc.response["Error"]["Code"] in ("404", "NoSuchKey"):
                    continue
                raise
            if h["ETag"] == obj["etag"] and h["ContentLength"] == obj["size"]:
                kept.append(obj)
        return kept

    # ── database ──────────────────────────────────────────────────────────

    def referenced_paths(self):
        # Só as colunas que já existem no banco: em produção uma migração pode
        # estar pendente e aí o campo novo ainda não é coluna.
        with connection.cursor() as cursor:
            columns = {
                c.name
                for c in connection.introspection.get_table_description(
                    cursor, ImageVariants._meta.db_table
                )
            }
        fields = [f for f in PATH_FIELDS if f in columns]
        paths = set()
        for row in ImageVariants.objects.values_list(*fields):
            paths.update(p.strip() for p in row if p and p.strip())
        return paths

    @staticmethod
    def to_path(key):
        return key.removeprefix(MEDIA_PREFIX)
