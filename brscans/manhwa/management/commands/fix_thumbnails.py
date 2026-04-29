from django.core.management.base import BaseCommand

from brscans.manhwa.models import ImageVariants, Manhwa
from brscans.manhwa.tasks.images_variants import add_original_image_variant
from brscans.wrapper import sources


class Command(BaseCommand):
    help = "Fix manhwas without thumbnails"

    def handle(self, *args, **options):
        # find manhwas without thumbnail or thumbnail original empty
        manhwas = Manhwa.objects.all()

        self.stdout.write(f"Found {manhwas.count()} manhwas to fix.")

        for manhwa in manhwas:
            if not manhwa.source:
                self.stdout.write(
                    f"Skipping {manhwa.title} (ID: {manhwa.pk}) - No source URL"
                )
                continue

            try:
                self.stdout.write(f"Fixing {manhwa.title} (ID: {manhwa.pk})")

                # Fetch info from source
                Source = sources.get_source_by_link(manhwa.source)
                if not Source:
                    self.stdout.write(
                        f"  Failed: Could not find source for '{manhwa.source}'"
                    )
                    continue

                result = Source.info(manhwa.source, capthers=False)
                image_url = result.get("image")

                if not image_url:
                    self.stdout.write(
                        f"  Failed: No image found in source '{manhwa.source}'"
                    )
                    continue

                # Create variant if null
                if getattr(manhwa, "thumbnail", None) is None:
                    thumbnail = ImageVariants.objects.create()
                    manhwa.thumbnail = thumbnail
                    manhwa.save()

                # Setup variant async
                add_original_image_variant(
                    manhwa.thumbnail.pk,
                    image_url,
                    ["chapters", str(manhwa.pk)],
                    False,
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"  Successfully dispatched thumbnail update for {manhwa.title}"
                    )
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"  Error processing {manhwa.title}: {e}")
                )

        self.stdout.write(self.style.SUCCESS("Finished fixing thumbnails!"))
