"""Starts the real LiteLLM proxy with litellm_config.yaml against fake Bedrock and OpenRouter.

Skipped when the `litellm` command is not installed (CI installs the pinned version).
Checks: the key is enforced; private models call Bedrock signed for Sydney; private models
fall back only to private models; tools reach Bedrock and tool calls come back; OpenRouter
requests ask for zero data retention; the daily Bedrock budget blocks further calls.
"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from tests.helpers import STACK

LITELLM = shutil.which("litellm")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeServer:
    """Records every request; subclasses decide the response."""

    def __init__(self):
        self.calls: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
                call = {"path": unquote(self.path), "auth": self.headers.get("authorization", ""), "body": body}
                outer.calls.append(call)
                status, payload = outer.respond(call)
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class FakeBedrock(FakeServer):
    """Bedrock Converse API: POST /model/{modelId}/converse."""

    def __init__(self):
        self.failing: set[str] = set()
        super().__init__()

    def model_ids(self) -> list[str]:
        return [re.match(r"/model/(.+)/converse", c["path"]).group(1) for c in self.calls]

    def respond(self, call):
        model = re.match(r"/model/(.+)/converse", call["path"]).group(1)
        if model in self.failing:
            return 500, {"message": "model down"}
        usage = {"inputTokens": 1000, "outputTokens": 1000, "totalTokens": 2000}
        if "toolConfig" in call["body"]:
            name = call["body"]["toolConfig"]["tools"][0]["toolSpec"]["name"]
            content = [{"toolUse": {"toolUseId": "t1", "name": name, "input": {"city": "Auckland"}}}]
            return 200, {"output": {"message": {"role": "assistant", "content": content}},
                         "stopReason": "tool_use", "usage": usage}
        return 200, {"output": {"message": {"role": "assistant", "content": [{"text": f"OK from {model}"}]}},
                     "stopReason": "end_turn", "usage": usage}


class FakeOpenRouter(FakeServer):
    def respond(self, call):
        return 200, {
            "id": "x", "object": "chat.completion", "created": int(time.time()), "model": call["body"].get("model"),
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "OK from openrouter"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        }


@unittest.skipUnless(LITELLM, "litellm not installed")
class GatewayTests(unittest.TestCase):
    KEY = "sk-integration-test-key"

    @classmethod
    def setUpClass(cls):
        cls.bedrock = FakeBedrock()
        cls.openrouter = FakeOpenRouter()
        cls.tmp = tempfile.TemporaryDirectory()
        # Small Bedrock budget so the last test can cross it (each fake call is ~$0.002).
        config = (STACK / "litellm_config.yaml").read_text()
        bedrock_budget = "    bedrock:\n      budget_limit: 3.0 "
        assert bedrock_budget in config
        config = config.replace(bedrock_budget, "    bedrock:\n      budget_limit: 0.04 ")
        cfg = Path(cls.tmp.name) / "config.yaml"
        cfg.write_text(config)
        cls.port = free_port()
        cls.env = dict(
            os.environ,
            AWS_ACCESS_KEY_ID="AKIAFAKEFORTESTS", AWS_SECRET_ACCESS_KEY="fake-secret",
            AWS_BEDROCK_RUNTIME_ENDPOINT=cls.bedrock.url,  # test-only redirect of Bedrock
            OPENROUTER_API_KEY="sk-or-fake", OPENROUTER_API_BASE=cls.openrouter.url + "/v1",
            LITELLM_MASTER_KEY=cls.KEY, LITELLM_LOCAL_MODEL_COST_MAP="True",
        )
        for var in ("AWS_PROFILE", "AWS_SESSION_TOKEN", "AWS_REGION", "AWS_DEFAULT_REGION"):
            cls.env.pop(var, None)
        cls.log = open(Path(cls.tmp.name) / "litellm.log", "w")
        cls.proc = subprocess.Popen([LITELLM, "--config", str(cfg), "--host", "127.0.0.1", "--port", str(cls.port)],
                                    env=cls.env, stdout=cls.log, stderr=subprocess.STDOUT)
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
        cls.bedrock.close()
        cls.openrouter.close()
        cls.tmp.cleanup()

    def setUp(self):
        self.bedrock.calls.clear()
        self.bedrock.failing.clear()
        self.openrouter.calls.clear()

    def chat(self, model: str, key: str | None = KEY, **extra):
        payload = {"model": model, "messages": [{"role": "user", "content": "hi"}], **extra}
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/v1/chat/completions",
            data=json.dumps(payload).encode(),
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
            status, _ = self.chat("private-coder", key)
            self.assertGreaterEqual(status, 400, key)
        self.assertEqual(self.bedrock.calls, [])

    def test_2_private_models_call_bedrock_signed_for_sydney(self):
        expected = {
            "private-coder": "qwen.qwen3-coder-next",
            "private-coder-lite": "qwen.qwen3-coder-30b-a3b-v1:0",
            "private-general": "qwen.qwen3-235b-a22b-2507-v1:0",
            "private-reasoner": "deepseek.v3.2",
        }
        for name, model_id in expected.items():
            status, body = self.chat(name)
            self.assertEqual(status, 200, body)
            self.assertEqual(body["choices"][0]["message"]["content"], f"OK from {model_id}")
        self.assertEqual(self.bedrock.model_ids(), list(expected.values()))
        for call in self.bedrock.calls:
            self.assertIn("/ap-southeast-2/bedrock/aws4_request", call["auth"])
        self.assertEqual(self.openrouter.calls, [])

    def test_3_private_falls_back_only_to_private(self):
        self.bedrock.failing.add("qwen.qwen3-coder-next")
        for name in ("private-coder", "local-coder", "hybrid-agent"):
            status, body = self.chat(name)
            self.assertEqual(status, 200, (name, body))
            self.assertEqual(body["choices"][0]["message"]["content"], "OK from qwen.qwen3-coder-30b-a3b-v1:0")
        # When every private model is down, the request fails rather than leaving Bedrock.
        self.bedrock.failing.update({"qwen.qwen3-coder-30b-a3b-v1:0", "qwen.qwen3-235b-a22b-2507-v1:0",
                                     "deepseek.v3.2"})
        for name in ("private-coder", "private-general", "private-reasoner"):
            status, _ = self.chat(name)
            self.assertGreaterEqual(status, 500, name)
        self.assertEqual(self.openrouter.calls, [])

    def test_4_check_models_script_sees_answers_and_tool_calls(self):
        env_file = Path(self.tmp.name) / ".env"
        env_file.write_text(f"LITELLM_MASTER_KEY={self.KEY}\nLITELLM_BASE_URL=http://127.0.0.1:{self.port}/v1\n")
        res = subprocess.run([sys.executable, str(STACK / "scripts" / "check_models.py"), "--env", str(env_file)],
                             capture_output=True, text=True, timeout=300)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        lines = res.stdout.strip().splitlines()
        self.assertEqual(len(lines), 4, res.stdout)
        for line in lines:
            self.assertRegex(line, r"^ok .*answer ok.*tools ok")
        self.assertTrue(any("toolConfig" in c["body"] for c in self.bedrock.calls))

    def test_5_openrouter_requests_ask_for_zero_data_retention(self):
        status, body = self.chat("open-qwen")
        self.assertEqual(status, 200, body)
        self.assertEqual(self.openrouter.calls[0]["body"].get("provider"), {"zdr": True})
        self.assertEqual(self.bedrock.calls, [])

    def test_9_bedrock_budget_blocks_further_calls(self):
        statuses = [self.chat("private-general")[0] for _ in range(30)]
        self.assertIn(429, statuses, statuses)
        self.assertEqual(self.openrouter.calls, [])


if __name__ == "__main__":
    unittest.main()
