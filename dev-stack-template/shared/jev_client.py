"""
TypeSafe Jev client via OpenRouter Decisions API.

Jev does NOT generate text. It answers typed questions about a state
and returns calibrated probabilities (noul / choice / score).

Use it for cheap routing, urgency detection, classification, scoring
before calling expensive chat models.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_MODEL = "~typesafe/jev-latest"


async def jev_decide(
    state: str | dict | list,
    questions: dict[str, dict],
    model: str = DEFAULT_MODEL,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """
    Call Jev Decisions API.

    Example questions:
    {
      "is_urgent": {
        "type": "noul",
        "instructions": "Does this convey urgency?",
        "criteria": {"true": "Time-sensitive", "false": "No urgency"}
      },
      "route": {
        "type": "choice",
        "instructions": "Which specialist should handle this?",
        "criteria": {
          "coding": "Code, bugs, architecture",
          "research": "Trends, data, analysis",
          "support": "User questions, mentoring"
        }
      }
    }
    """
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set in environment")

    payload = {
        "model": model,
        "state": state,
        "questions": questions,
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            DECISIONS_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:3000",
                "X-Title": "DevStack-Jev",
            },
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


def jev_decide_sync(
    state: str | dict | list,
    questions: dict[str, dict],
    model: str = DEFAULT_MODEL,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Synchronous wrapper for simple scripts."""
    import asyncio
    return asyncio.run(jev_decide(state, questions, model, timeout))


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


async def route_request(user_text: str) -> dict[str, Any]:
    """Quick router for multi-agent systems."""
    return await jev_decide(state=user_text, questions=ROUTE_QUESTIONS)


if __name__ == "__main__":
    import json
    sample = "Help me plan a 4-week study schedule for calculus for my son."
    result = jev_decide_sync(sample, ROUTE_QUESTIONS)
    print(json.dumps(result, indent=2))
