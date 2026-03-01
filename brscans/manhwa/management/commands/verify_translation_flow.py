from django.core.management.base import BaseCommand

from brscans.manhwa.models import Chapter, Page


class Command(BaseCommand):
    help = "Verify the results of the translation pipeline test"

    def add_arguments(self, parser):
        parser.add_argument(
            "--chapter_id",
            type=int,
            required=False,
            help="Specific test chapter ID to check",
        )

    def handle(self, *args, **options):
        chapter_id = options.get("chapter_id")

        if chapter_id:
            chapters = Chapter.objects.filter(pk=chapter_id)
        else:
            # Find all test chapters
            chapters = Chapter.objects.filter(
                title__startswith="Test Clone of "
            ).order_by("id")

        if not chapters.exists():
            self.stdout.write(
                self.style.ERROR(
                    "No test chapter found. Run test_translation_flow first."
                )
            )
            return

        for chapter in chapters:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nChecking Chapter: {chapter.title} (ID: {chapter.pk})"
                )
            )

            pages = Page.objects.filter(chapter=chapter).order_by("order")
            total = pages.count()
            translated_count = 0
            raw_count = 0

            for page in pages:
                variant = page.images
                if not variant:
                    self.stdout.write(f"Page {page.order}: No ImageVariant")
                    continue

                has_original = bool(variant.original)
                has_raw = bool(variant.raw)
                has_translated = bool(variant.translated)

                status = []
                if has_original:
                    status.append("original: OK")
                else:
                    status.append("original: MISSING")

                if has_raw:
                    status.append("raw: OK")
                    raw_count += 1
                else:
                    status.append("raw: -")

                if has_translated:
                    status.append("translated: OK")
                    translated_count += 1
                else:
                    status.append("translated: PENDING/MISSING")

                msg = (
                    f"Page {page.order:02d} (Variant {variant.pk}): "
                    + " | ".join(status)
                )
                if has_translated:
                    self.stdout.write(self.style.SUCCESS(msg))
                elif has_raw:
                    self.stdout.write(self.style.WARNING(msg))
                else:
                    self.stdout.write(self.style.ERROR(msg))

            self.stdout.write(
                self.style.SUCCESS(
                    f"Summary: {translated_count}/{total} pages translated (Raw: {raw_count}/{total})."
                )
            )
            if translated_count == total and total > 0:
                self.stdout.write(
                    self.style.SUCCESS("PIPELINE TEST PASSED/COMPLETE!")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        "PIPELINE TEST STILL RUNNING OR FAILED! Some pages missing translations."
                    )
                )
