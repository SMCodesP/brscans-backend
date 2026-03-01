from concurrent.futures import ThreadPoolExecutor

from django.core.management.base import BaseCommand

from brscans.manhwa.models import Chapter, ImageVariants, Manhwa, Page
from brscans.manhwa.tasks.images_variants import process_image_translate


class Command(BaseCommand):
    help = "Clone a chapter and trigger translation pipeline for testing"

    def handle(self, *args, **options):
        manhwa_id = 182
        chapter_ids = [5454]

        source_manhwa = Manhwa.objects.filter(id=manhwa_id).first()
        if not source_manhwa:
            self.stdout.write(
                self.style.ERROR(f"Source Manhwa {manhwa_id} not found.")
            )
            return

        test_manhwa, _ = Manhwa.objects.get_or_create(
            title="Test Pipeline Bug Manhwa",
            defaults={
                "status": "Test",
                "description": "Used for testing translation pipeline",
            },
        )

        old_test_chapters = Chapter.objects.filter(manhwa=test_manhwa)
        for otc in old_test_chapters:
            self.stdout.write(
                self.style.WARNING(f"Deleting old test chapter {otc.pk}")
            )
            otc.delete()

        def process_chapter(c_id):
            source_chapter = Chapter.objects.filter(pk=c_id).first()
            if not source_chapter:
                self.stdout.write(
                    self.style.ERROR(f"Source Chapter {c_id} not found.")
                )
                return

            test_chapter = Chapter.objects.create(
                title=f"Test Clone of {source_chapter.title}",
                manhwa=test_manhwa,
                source=source_chapter.source,
                quantity_pages=source_chapter.quantity_pages,
            )

            self.proccess_test_chapter(
                test_manhwa, test_chapter, source_chapter
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"All translations triggered. Test Chapter ID: {test_chapter.pk}"
                )
            )

        with ThreadPoolExecutor() as executor:
            executor.map(process_chapter, chapter_ids)

    def proccess_test_chapter(self, test_manhwa, test_chapter, source_chapter):
        source_pages = Page.objects.filter(chapter=source_chapter).order_by(
            "order"
        )

        cloned_variants = []

        self.stdout.write(
            self.style.SUCCESS(f"Cloning {source_pages.count()} pages...")
        )

        for sp in source_pages:
            if not sp.images or not sp.images.original:
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipping page {sp.order} because no original."
                    )
                )
                continue

            new_variant = ImageVariants.objects.create()
            new_variant.original.name = sp.images.original.name
            new_variant.save()

            # create page record
            Page.objects.create(
                chapter=test_chapter,
                images=new_variant,
                order=sp.order,
                quantity_merged=sp.quantity_merged,
            )

            cloned_variants.append(new_variant)

        self.stdout.write(
            self.style.SUCCESS(
                f"Triggering translation for {len(cloned_variants)} pages..."
            )
        )

        def proccess_merged(variant):
            folder = ["chapters", str(test_chapter.pk)]
            self.stdout.write(
                f"Processing translate for variant {variant.pk} ..."
            )
            process_image_translate(
                variant.pk, variant.original.url, folder, test_manhwa.id
            )

        with ThreadPoolExecutor() as executor:
            executor.map(proccess_merged, cloned_variants)
