"""Disparo ao Modal não pode segurar a Lambda nem duplicar o trabalho.

O contrato do `_post_ack` (429/5xx e conexão retentam; ReadTimeout e 4xx não)
é testado em test_task_dispatch.py, onde a função compartilhada mora.
"""

from unittest import mock

from django.test import SimpleTestCase, override_settings

from brscans.manhwa.tasks import images_variants as tasks


@override_settings(
    PUBLIC_MEDIA_LOCATION="media/",
    TRANSLATOR_URL="http://translator-ack",
    FILL_URL="http://fill-ack",
)
class DispatcherTests(SimpleTestCase):
    @mock.patch.object(tasks, "generate_presigned_url", return_value="http://s3")
    @mock.patch.object(tasks, "image_destination", return_value=("p", "webp"))
    def test_translate_posts_to_the_ack_endpoint(self, *_):
        with mock.patch.object(tasks, "_post_ack", return_value={}) as post:
            tasks.process_image_translate.sync(7, "http://img", ["chapters", "1"])
        self.assertEqual(post.call_args.args[0], "http://translator-ack")
        self.assertEqual(post.call_args.args[1]["image_id"], 7)
