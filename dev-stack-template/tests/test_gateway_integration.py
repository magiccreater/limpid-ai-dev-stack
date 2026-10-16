"""Starts the real LiteLLM proxy with litellm_config.yaml against fake model servers.

Skipped when the `litellm` command is not installed (CI installs the pinned version).
Checks: the key is enforced, hybrid falls back when local fails, budgets block spending.
"""

import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from tests.helpers import STACK

LITELLM = shutil.which("litellm")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeModel:
    """Minimal OpenAI-compatible server that records calls and can fail."""

    def __init__(self, name: str, fail: bool = False):
        self.name, self.fail, self.calls = name, fail, []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
                outer.calls.append(body.get("model"))
                if outer.fail:
                    self.send_response(500)
                    self.end_headers()
                    return
                data = json.dumps({
                    "id": "x", "object": "chat.completion", "created": int(time.time()), "model": body.get("model"),
                    "choices": [{"index": 0, "finish_reason": "stop",
                                 "message": {"role": "assistant", "content": f"from {outer.name}"}}],
                    "usage": {"prompt_tokens": 1000, "completion_tokens": 1000, "total_tokens": 2000},
                }).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@unittest.skipUnless(LITELLM, "litellm not installed")
class GatewayTests(unittest.TestCase):
    KEY = "sk-integration-test-key"

    @classmethod
    def setUpClass(cls):
        cls.local = FakeModel("local", fail=True)
        cls.cloud = FakeModel("openrouter")
        cls.tmp = tempfile.TemporaryDirectory()
        # Tiny budget so two calls cross it: each fake call costs about $0.0014 at
        # deepseek prices (1000 in + 1000 out tokens).
        config = (STACK / "litellm_config.yaml").read_text().replace(
            "budget_limit: 3.0 ", "budget_limit: 0.002 ")
        assert "budget_limit: 0.002" in config
        cfg = Path(cls.tmp.name) / "config.yaml"
        cfg.write_text(config)
        cls.port = free_port()
        env = dict(os.environ, LOCAL_LLM_BASE_URL=cls.local.url, OPENROUTER_API_KEY="sk-or-fake",
                   OPENROUTER_API_BASE=cls.cloud.url, LITELLM_MASTER_KEY=cls.KEY,
                   LITELLM_LOCAL_MODEL_COST_MAP="True")
        cls.log = open(Path(cls.tmp.name) / "litellm.log", "w")
        cls.proc = subprocess.Popen([LITELLM, "--config", str(cfg), "--host", "127.0.0.1", "--port", str(cls.port)],
                                    env=env, stdout=cls.log, stderr=subprocess.STDOUT)
        deadline = time.time() + 120
        while time.time() < deadline:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{cls.port}/health/liveliness", timeout=2)
                return
            except OSError:
                time.sleep(1)
        cls.tearDownClass()
        raise RuntimeError("litellm did not start")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=30)
        cls.log.close()
        cls.local.close()
        cls.cloud.close()
        cls.tmp.cleanup()

    def chat(self, model: str, key: str | None = KEY):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/v1/chat/completions",
            data=json.dumps({"model": model, "messages": [{"role": "user", "content": "hi"}]}).encode(),
            headers={"content-type": "application/json", **({"authorization": f"Bearer {key}"} if key else {})},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, {"raw": raw.decode(errors="replace")}

    def test_1_requests_without_the_key_are_rejected(self):
        for key in (None, "sk-dev-proxy-key"):
            status, _ = self.chat("open-deepseek", key)
            self.assertGreaterEqual(status, 400, key)
        self.assertEqual(self.cloud.calls, [])

    def test_2_hybrid_falls_back_to_open_model_when_local_fails(self):
        status, body = self.chat("hybrid-agent")
        self.assertEqual(status, 200, body)
        self.assertEqual(body["choices"][0]["message"]["content"], "from openrouter")
        self.assertIn("local", self.local.calls)
        self.assertEqual(self.cloud.calls[-1], "deepseek/deepseek-v4-flash")

    def test_3_budget_blocks_further_openrouter_calls(self):
        statuses = [self.chat("open-qwen")[0] for _ in range(3)]
        self.assertIn(429, statuses, statuses)


if __name__ == "__main__":
    unittest.main()
