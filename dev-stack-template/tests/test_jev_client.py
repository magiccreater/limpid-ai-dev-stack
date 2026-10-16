import asyncio
import json
import unittest
from unittest import mock

import httpx

from devstack_shared import jev_client

ENV = {"OPENROUTER_API_KEY": "sk-or-test", "JEV_ENABLED": "1"}


def client_returning(status=200, body=None, calls=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        if isinstance(body, (dict, list)):
            return httpx.Response(status, json=body)
        return httpx.Response(status, text=body or "")
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def run(coro):
    return asyncio.run(coro)


GOOD = {
    "id": "x",
    "answers": {
        "route": {"type": "choice", "choice": "study", "confidence": 0.9},
        "complexity": {"type": "score", "score": 1.99, "confidence": 0.9},
    },
    "usage": {"cost": 0.00002},
}


@mock.patch.object(jev_client, "load_env", lambda: None)
class RouteTests(unittest.TestCase):
    def test_success_parses_answers_and_sends_object_state(self):
        calls = []
        with mock.patch.dict("os.environ", ENV, clear=True):
            d = run(jev_client.route_request("plan calculus", client=client_returning(body=GOOD, calls=calls)))
        self.assertEqual((d.route, d.complexity, d.source), ("study", 1.99, "jev"))
        sent = json.loads(calls[0].content)
        self.assertEqual(sent["state"], {"request": "plan calculus"})
        self.assertEqual(sent["model"], "~typesafe/jev-latest")
        self.assertEqual(str(calls[0].url), jev_client.DECISIONS_URL)
        self.assertEqual(calls[0].headers["authorization"], "Bearer sk-or-test")

    def test_disabled_or_no_key_falls_back_without_network(self):
        for env in ({"OPENROUTER_API_KEY": "k", "JEV_ENABLED": "0"}, {}):
            calls = []
            with mock.patch.dict("os.environ", env, clear=True):
                d = run(jev_client.route_request("x", client=client_returning(body=GOOD, calls=calls)))
            self.assertEqual((d.route, d.complexity, d.source), ("coding", 1.0, "fallback"))
            self.assertEqual(calls, [])

    def test_http_errors_and_bad_bodies_fall_back(self):
        for status, body in ((500, "boom"), (401, {"error": "bad key"}), (200, "not json"),
                             (200, {"no": "answers"}), (200, [1, 2])):
            with mock.patch.dict("os.environ", ENV, clear=True):
                d = run(jev_client.route_request("x", client=client_returning(status, body)))
            self.assertEqual(d.source, "fallback", (status, body))

    def test_network_error_falls_back(self):
        def boom(request):
            raise httpx.ConnectError("offline")
        client = httpx.AsyncClient(transport=httpx.MockTransport(boom))
        with mock.patch.dict("os.environ", ENV, clear=True):
            d = run(jev_client.route_request("x", client=client))
        self.assertEqual(d.source, "fallback")
        self.assertIn("offline", d.reason)

    def test_unknown_route_and_out_of_range_score_use_defaults(self):
        for score in (7, -1, "2", None, True):
            body = {"answers": {"route": {"choice": "hack-the-planet"}, "complexity": {"score": score}}}
            with mock.patch.dict("os.environ", ENV, clear=True):
                d = run(jev_client.route_request("x", client=client_returning(body=body)))
            self.assertEqual((d.route, d.complexity, d.source), ("coding", 1.0, "jev"), score)

    def test_try_decide_returns_answers_or_none(self):
        with mock.patch.dict("os.environ", ENV, clear=True):
            self.assertEqual(run(jev_client.try_decide("x", {}, client=client_returning(body=GOOD))), GOOD["answers"])
            self.assertIsNone(run(jev_client.try_decide("x", {}, client=client_returning(503, "down"))))

    def test_jev_decide_still_raises_for_callers_that_want_errors(self):
        with mock.patch.dict("os.environ", ENV, clear=True):
            with self.assertRaises(httpx.HTTPStatusError):
                run(jev_client.jev_decide("x", {}, client=client_returning(500, "boom")))
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(jev_client.JevUnavailable):
                run(jev_client.jev_decide("x", {}))


if __name__ == "__main__":
    unittest.main()
