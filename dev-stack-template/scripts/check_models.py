#!/usr/bin/env python3
"""Call each model through the LiteLLM gateway and report whether it answers and calls tools.

  python3 scripts/check_models.py                    # the five private Bedrock models
  python3 scripts/check_models.py open-deepseek      # any model names from litellm_config.yaml
  python3 scripts/check_models.py --no-tools private-coder

Each check sends two tiny requests (a fraction of a cent). Standard library only.
Exit code 1 if any model fails the basic answer check.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from devstack_env import parse  # noqa: E402

PRIVATE_MODELS = ["private-coder", "private-coder-lite", "private-general", "private-reasoner", "private-glm"]

TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather for a city.",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}


def post(base: str, key: str, payload: dict, timeout: float) -> tuple[dict, float]:
    req = urllib.request.Request(
        f"{base.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp), time.monotonic() - started
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            message = json.loads(raw).get("error", {}).get("message", raw)
        except ValueError:
            message = raw
        raise RuntimeError(f"HTTP {exc.code}: {message[:300]}") from None


def check(base: str, key: str, model: str, tools: bool, timeout: float) -> tuple[bool, str]:
    try:
        body, secs = post(base, key, {
            "model": model,
            "messages": [{"role": "user", "content": "Reply with the single word OK."}],
            "max_tokens": 20,
        }, timeout)
        text = (body["choices"][0]["message"].get("content") or "").strip()
        served_by = body.get("model", "?")
        result = f"answer ok ({secs:.1f}s, served by {served_by}): {text[:40]!r}"
    except Exception as exc:  # report every failure the same way
        return False, f"answer FAILED: {exc}"

    if tools:
        try:
            body, secs = post(base, key, {
                "model": model,
                "messages": [{"role": "user", "content": "What is the weather in Auckland? Use the tool."}],
                "tools": [TOOL],
                "max_tokens": 200,
            }, timeout)
            calls = body["choices"][0]["message"].get("tool_calls") or []
            names = [c.get("function", {}).get("name") for c in calls]
            result += f"; tools {'ok' if 'get_weather' in names else 'NOT USED'} ({secs:.1f}s)"
        except Exception as exc:
            result += f"; tools FAILED: {exc}"
    return True, result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("models", nargs="*", default=PRIVATE_MODELS)
    ap.add_argument("--no-tools", action="store_true", help="skip the tool-calling check")
    ap.add_argument("--env", default=str(Path(__file__).resolve().parents[1] / ".env"))
    ap.add_argument("--timeout", type=float, default=120)
    args = ap.parse_args(argv)

    env = parse(Path(args.env).read_text(encoding="utf-8")) if Path(args.env).exists() else {}
    base = env.get("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
    key = env.get("LITELLM_MASTER_KEY", "")
    if not key:
        print("LITELLM_MASTER_KEY not found; run: just env", file=sys.stderr)
        return 1

    failed = 0
    for model in args.models:
        ok, line = check(base, key, model, not args.no_tools, args.timeout)
        failed += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {model:20} {line}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
