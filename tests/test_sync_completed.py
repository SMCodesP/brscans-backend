from unittest import mock

from django.test import TestCase

from brscans.manhwa.models import Manhwa, ManhwaStatus
from brscans.manhwa.tasks.sync_chapters import sync_chapters


class SyncCompletedTest(TestCase):
    def test_completed_manhwa_is_not_synced(self):
        manhwa = Manhwa.objects.create(
            title="m", description="d", status=ManhwaStatus.COMPLETED,
            source="https://example.com/m",
        )
        with mock.patch("brscans.manhwa.tasks.sync_chapters.sources.get_source_by_link") as get_source:
            sync_chapters.__wrapped__(manhwa.pk)
        get_source.assert_not_called()
