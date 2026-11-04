import os
from unittest import mock

import httpx
from django.test import TestCase

from brscans.manhwa import discord
from brscans.manhwa.models import Chapter, Manhwa
from brscans.manhwa.work import DONE


def _chapters(manhwa, numbers, **fields):
    for number in numbers:
        Chapter.objects.create(
            manhwa=manhwa,
            title=f"Chapter {number}",
            slug=f"chapter-{number}",
            work_status=fields.get("status", DONE),
        )


@mock.patch.dict(
    os.environ, {"DISCORD_BOT_TOKEN": "t", "DISCORD_CHANNEL_ID": "1"}
)
class NotifyTests(TestCase):
    def setUp(self):
        self.manhwa = Manhwa.objects.create(title="Solo", identifier="a")
        patcher = mock.patch.object(discord, "_send")
        self.send = patcher.start()
        self.addCleanup(patcher.stop)

    def test_three_or_more_become_one_ordered_message(self):
        _chapters(self.manhwa, [12, 10, 11])
        self.assertEqual(discord.notify_finished_chapters()["sent"], 1)
        batch = self.send.call_args.args[3]
        self.assertEqual(
            [discord.chapter_number(c) for c in batch], ["10", "11", "12"]
        )
        embed = discord.build_embed(self.manhwa, batch)
        self.assertIn("10, 11, 12", embed["description"])

    def test_two_are_separate_messages(self):
        _chapters(self.manhwa, [1, 2])
        self.assertEqual(discord.notify_finished_chapters()["sent"], 2)

    def test_incomplete_chapter_waits(self):
        _chapters(self.manhwa, [1], status="running")
        self.assertEqual(discord.notify_finished_chapters()["sent"], 0)
        self.assertFalse(Chapter.objects.get().discord_notified)

    def test_nsfw_is_never_sent(self):
        nsfw = Manhwa.objects.create(title="X", identifier="b", is_nsfw=True)
        _chapters(nsfw, [1])
        result = discord.notify_finished_chapters()
        self.assertEqual((result["sent"], result["skipped_nsfw"]), (0, 1))
        self.send.assert_not_called()

    def test_notifies_only_once(self):
        _chapters(self.manhwa, [1])
        discord.notify_finished_chapters()
        self.assertEqual(discord.notify_finished_chapters()["sent"], 0)

    def test_failure_retries_next_run(self):
        _chapters(self.manhwa, [1])
        self.send.side_effect = httpx.ConnectError("x")
        self.assertTrue(discord.notify_finished_chapters()["error"])
        self.assertFalse(Chapter.objects.get().discord_notified)
