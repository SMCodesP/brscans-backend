"""
Management command to find and delete S3 chapter folders
that no longer have a corresponding Chapter record in the database.

Usage:
    # Dry-run (list ghost folders only):
    python manage.py cleanup_ghost_chapters

    # Actually delete ghost folders:
    python manage.py cleanup_ghost_chapters --delete
"""

from django.core.management.base import BaseCommand

from brscans.manhwa.models import Chapter
from brscans.services.s3 import s3_client

BUCKET = "brscans-media"
PREFIX = "media/chapters/"


class Command(BaseCommand):
    help = "Find and delete S3 chapter folders that no longer exist in the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Actually delete the ghost folders. Without this flag, only lists them.",
        )

    def handle(self, *args, **options):
        should_delete = options["delete"]

        self.stdout.write(
            self.style.NOTICE("Listing S3 prefixes under media/chapters/ ...")
        )

        # 1. Collect all chapter folder names from S3
        s3_chapter_ids = set()
        paginator = s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=BUCKET, Prefix=PREFIX, Delimiter="/")

        for page in pages:
            for prefix_obj in page.get("CommonPrefixes", []):
                # prefix_obj["Prefix"] looks like "media/chapters/123/"
                folder_name = prefix_obj["Prefix"].rstrip("/").split("/")[-1]
                s3_chapter_ids.add(folder_name)

        self.stdout.write(f"  Found {len(s3_chapter_ids)} folders in S3.")

        # 2. Get all existing chapter PKs from the database
        db_chapter_ids = set(
            str(pk) for pk in Chapter.objects.values_list("pk", flat=True)
        )
        self.stdout.write(
            f"  Found {len(db_chapter_ids)} chapters in the database."
        )

        # 3. Compute ghost folders
        ghost_ids = s3_chapter_ids - db_chapter_ids
        self.stdout.write(
            self.style.WARNING(
                f"\n  Ghost folders (in S3 but not in DB): {len(ghost_ids)}"
            )
        )

        if not ghost_ids:
            self.stdout.write(
                self.style.SUCCESS("\n  No ghost folders found. Nothing to do!")
            )
            return

        for gid in sorted(
            ghost_ids, key=lambda x: int(x) if x.isdigit() else x
        ):
            self.stdout.write(f"    s3://{BUCKET}/{PREFIX}{gid}/")

        # 4. Delete if requested
        if not should_delete:
            self.stdout.write(
                self.style.NOTICE(
                    "\n  Dry-run mode. Run with --delete to remove these folders."
                )
            )
            return

        self.stdout.write(self.style.WARNING("\n  Deleting ghost folders..."))
        deleted_count = 0

        for gid in sorted(
            ghost_ids, key=lambda x: int(x) if x.isdigit() else x
        ):
            folder_prefix = f"{PREFIX}{gid}/"
            objects_to_delete = []

            # List all objects under this prefix
            obj_pages = paginator.paginate(Bucket=BUCKET, Prefix=folder_prefix)
            for obj_page in obj_pages:
                for obj in obj_page.get("Contents", []):
                    objects_to_delete.append({"Key": obj["Key"]})

            if not objects_to_delete:
                continue

            # Delete in batches of 1000 (S3 limit)
            for i in range(0, len(objects_to_delete), 1000):
                batch = objects_to_delete[i : i + 1000]
                s3_client.delete_objects(
                    Bucket=BUCKET,
                    Delete={"Objects": batch},
                )

            self.stdout.write(
                f"    Deleted {len(objects_to_delete)} objects from {folder_prefix}"
            )
            deleted_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\n  Done! Deleted {deleted_count} ghost chapter folders."
            )
        )
