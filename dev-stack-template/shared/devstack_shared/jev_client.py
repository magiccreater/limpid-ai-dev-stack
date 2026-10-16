"""
TypeSafe Jev client (OpenRouter Decisions API).

Jev does not generate text. It answers typed questions about a state and returns
calibrated probabilities (noul / choice / score). Use it for cheap routing and
classification before calling a chat model.

Privacy: every call sends the state to OpenRouter. Set JEV_ENABLED=0 in .env when
agents handle client or private data; route_request() then uses local defaults.

Failure: route_request() and try_decide() never raise. When Jev is disabled, has no
key, or fails, they return a fallback so the agent keeps working.
"""

from __future__ import annotations

import math
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from .config import load_env

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_MODEL = "~typesafe/jev-latest"


class JevUnavailable(RuntimeError):
    """Jev is disabled, has no key, or returned something unusable."""


def jev_enabled(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return env.get("JEV_ENABLED", "1").strip() != "0" and bool(env.get("OPENROUTER_API_KEY"))


def as_state(state: str | dict | list) -> dict | list:
    """Jev takes a JSON object of named fields; wrap plain text in one."""
    return {"request": state} if isinstance(state, str) else state


async def jev_decide(
    state: str | dict | list,
    questions: dict[str, dict],
    model: str | None = None,
    timeout: float = 15.0,
    *,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Call the Decisions API. Raises JevUnavailable or httpx errors on failure."""
    load_env()
    if not jev_enabled():
        raise JevUnavailable("Jev is disabled (JEV_ENABLED=0) or OPENROUTER_API_KEY is not set")

    payload = {
        "model": model or os.getenv("JEV_MODEL", DEFAULT_MODEL),
        "state": as_state(state),
        "questions": questions,
    }
    headers = {
        "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
        "Content-Type": "application/json",
        "X-Title": "DevStack-Jev",
    }
    url = os.getenv("JEV_URL", DECISIONS_URL)

    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=timeout)
    try:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    finally:
        if owns_client:
            await client.aclose()

    if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
        raise JevUnavailable("Jev response has no 'answers' object")
    return data


def jev_decide_sync(
    state: str | dict | list,
    questions: dict[str, dict],
    model: str | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Synchronous wrapper for simple scripts."""
    import asyncio

    return asyncio.run(jev_decide(state, questions, model, timeout))


_EXPECTED_FAILURES = (JevUnavailable, httpx.HTTPError, ValueError, KeyError, TypeError)


def _warn(msg: str) -> None:
    print(f"[jev] {msg}", file=sys.stderr)


async def try_decide(
    state: str | dict | list,
    questions: dict[str, dict],
    *,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any] | None:
    """Like jev_decide, but returns the answers dict, or None when Jev is unavailable."""
    try:
        return (await jev_decide(state, questions, client=client))["answers"]
    except _EXPECTED_FAILURES as exc:
        _warn(f"skipped: {str(exc)[:200]}")
        return None


# Convenience presets -------------------------------------------------

ROUTE_QUESTIONS = {
    "route": {
        "type": "choice",
        "instructions": "Which agent type should handle this request?",
        "criteria": {
            "coding": "Code generation, debugging, refactoring, architecture",
            "scraper": "Web scraping, data extraction, crawling",
            "social": "Social media posts, content creation, scheduling",
            "trend": "Trends, research, news digests",
            "stock": "Markets, stocks, trading signals, finance",
            "mentor": "Coaching, advice, personal development",
            "study": "Study plans, learning, education, spaced repetition",
            "gatekeeper": "Security review, XSS, SQL injection, passwords, hardening, DDoS defense advice",
            "support": "General questions, WhatsApp replies, help desk",
        },
    },
    "complexity": {
        "type": "score",
        "instructions": "How complex is this request? (0=trivial, 3=hard reasoning)",
        "criteria": {
            "0": "Simple lookup or short answer",
            "1": "Standard multi-step but routine",
            "2": "Requires research or careful reasoning",
            "3": "Hard multi-agent or long-horizon task",
        },
    },
}


@dataclass(frozen=True)
class RouteDecision:
    route: str
    complexity: float
    source: str          # "jev" or "fallback"
    reason: str = ""


async def route_request(
    user_text: str,
    default_route: str = "coding",
    default_complexity: float = 1.0,
    *,
    client: httpx.AsyncClient | None = None,
) -> RouteDecision:
    """Route a request with Jev. Never raises: falls back to the defaults instead."""
    try:
        data = await jev_decide(user_text, ROUTE_QUESTIONS, client=client)
        answers = data["answers"]
        route = answers.get("route", {}).get("choice")
        if route not in ROUTE_QUESTIONS["route"]["criteria"]:
            route = default_route
        complexity = answers.get("complexity", {}).get("score")
        if (
            not isinstance(complexity, (int, float))
            or isinstance(complexity, bool)
            or not math.isfinite(complexity)
            or not 0 <= complexity <= 3
        ):
            complexity = default_complexity
        return RouteDecision(route, float(complexity), "jev")
    except _EXPECTED_FAILURES as exc:
        reason = str(exc)[:200]
        _warn(f"routing fallback ({reason})")
        return RouteDecision(default_route, float(default_complexity), "fallback", reason)


if __name__ == "__main__":
    import asyncio

    sample = "Help me plan a 4-week study schedule for calculus for my son."
    print(asyncio.run(route_request(sample)))
