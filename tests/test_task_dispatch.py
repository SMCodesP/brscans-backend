"""Disparo de @task: Lambda de trabalho; fora da Lambda, fila local."""

import os
from unittest import mock

import httpx
from django.test import SimpleTestCase, override_settings

from brscans.utils import tasks


@tasks.task
def sample_task(value):
    return value


@override_settings(TASK_FUNCTION_NAME="worker")
class TaskDispatchTests(SimpleTestCase):
    def test_inside_lambda_invokes_the_worker(self):
        with mock.patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "dev"}):
            with mock.patch("zappa.asynchronous.run") as run:
                sample_task(1)
        self.assertEqual(
            run.call_args.kwargs["remote_aws_lambda_function_name"], "worker"
        )

    @override_settings(TASK_FUNCTION_NAME="")
    def test_missing_worker_name_fails_instead_of_using_the_api(self):
        with mock.patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "dev"}):
            with mock.patch("zappa.asynchronous.run") as run:
                with self.assertRaisesRegex(RuntimeError, "TASK_FUNCTION_NAME"):
                    sample_task(1)
        run.assert_not_called()

    def test_sync_runs_the_body(self):
        self.assertEqual(sample_task.sync(2), 2)

    def test_worker_runs_the_body_directly(self):
        """O zappa chama `func.sync` no worker — o merge não vira outro invoke.

        Se a worker enfileirasse de novo, o trabalho só sairia da fila para a
        API de 512 MB; `run_message` do zappa chama `.sync`, como aqui.
        """
        with mock.patch("zappa.asynchronous.run") as run:
            self.assertEqual(sample_task.sync(1), 1)
        run.assert_not_called()


class PostAckTests(SimpleTestCase):
    """429 do Modal é recusa, não falha do pedido: retenta e não perde a página."""

    def test_429_is_retried_then_accepted(self):
        responses = [
            httpx.Response(429),
            httpx.Response(202, json={"accepted": True}),
        ]
        with mock.patch("httpx.post", side_effect=responses) as post:
            with mock.patch.object(tasks.time, "sleep"):
                self.assertEqual(
                    tasks._post_ack("http://ack", {"image_id": 1}),
                    {"accepted": True},
                )
        self.assertEqual(post.call_count, 2)

    def test_read_timeout_is_not_retried(self):
        with mock.patch(
            "httpx.post", side_effect=httpx.ReadTimeout("slow")
        ) as post:
            with self.assertRaises(httpx.ReadTimeout):
                tasks._post_ack("http://ack", {"image_id": 1})
        self.assertEqual(post.call_count, 1)

    def test_429_after_all_attempts_raises_saturation(self):
        with mock.patch(
            "httpx.post", return_value=httpx.Response(429)
        ) as post:
            with mock.patch.object(tasks.time, "sleep"):
                with self.assertRaises(tasks.Saturation):
                    tasks._post_ack("http://ack", {"image_id": 1})
        self.assertEqual(post.call_count, 4)

    def test_contract_error_is_not_retried(self):
        with mock.patch(
            "httpx.post", return_value=httpx.Response(422)
        ) as post:
            with self.assertRaisesRegex(RuntimeError, "422"):
                tasks._post_ack("http://ack", {"image_id": 1})
        self.assertEqual(post.call_count, 1)


class PostAckTwoAccountsTests(SimpleTestCase):
    def _post(self, responses):
        calls = []

        def post(url, **kwargs):
            calls.append(url)
            return responses[url]

        with mock.patch.object(tasks.httpx, "post", side_effect=post):
            with mock.patch.object(tasks.time, "sleep"):
                result = tasks._post_ack("http://a,http://b", {"image_id": 7})
        return result, calls

    def test_image_id_splits_pages_between_accounts(self):
        ok = mock.Mock(status_code=200, content=b"{}", json=lambda: {})
        self.assertEqual(self._post({"http://b": ok})[1], ["http://b"])
        with mock.patch.object(tasks.httpx, "post", return_value=ok) as post:
            tasks._post_ack("http://a,http://b", {"image_id": 8})
        self.assertEqual(post.call_args.args[0], "http://a")

    def test_locked_account_falls_through_to_the_other(self):
        ok = mock.Mock(status_code=200, content=b"{}", json=lambda: {})
        locked = mock.Mock(status_code=403)
        _, calls = self._post({"http://b": locked, "http://a": ok})
        self.assertEqual(calls, ["http://b", "http://a"])

    def test_bad_request_does_not_change_account(self):
        with self.assertRaises(RuntimeError):
            self._post({"http://b": mock.Mock(status_code=422)})
