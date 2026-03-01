import json
from concurrent.futures import ThreadPoolExecutor

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Fill a chapter and trigger translation pipeline for testing"

    def handle(self, *args, **options):
        import os

        data_path = os.path.join(
            settings.BASE_DIR,
            "brscans",
            "manhwa",
            "management",
            "commands",
            "data.json",
        )

        with open(data_path, "r") as f:
            payloads = json.load(f)

        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded {len(payloads)} payloads from data.json"
            )
        )

        def process_payload(payload):
            self.stdout.write(
                f"Sending payload id {payload.get('id')} to fill server..."
            )
            try:
                res = httpx.post(
                    "https://9r4cs6g8pc.execute-api.sa-east-1.amazonaws.com/dev",
                    json=payload,
                    timeout=1.0,
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Response for {payload.get('id')}: {res.status_code} - {res.text}"
                    )
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Error for {payload.get('id')}: {e}")
                )

        with ThreadPoolExecutor() as executor:
            executor.map(process_payload, payloads)
