"""
Coding Agent — repo-aware helper that works with Cline / Aider / CLI.

Usage:
  cd examples/coding-agent
  uv sync
  uv run python agent.py "Add a health-check endpoint to the FastAPI app"
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.llm import get_llm
from shared.jev_client import route_request
import asyncio


SYSTEM = """You are an expert software engineer.
Prefer small, correct diffs. Explain trade-offs briefly.
When the task is large, break it into ordered steps first.
"""


async def run(task: str) -> str:
    routing = await route_request(task)
    answers = routing.get("answers", {})
    route = answers.get("route", {}).get("choice", "coding")
    complexity = answers.get("complexity", {}).get("score", 1)

    print(f"[Jev] route={route} complexity={complexity}")

    tier = "local" if complexity <= 1 else ("hybrid" if complexity <= 2 else "frontier")
    llm = get_llm(tier=tier)

    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": task},
    ]
    res = await llm.ainvoke(messages)
    return res.content


if __name__ == "__main__":
    task = " ".join(sys.argv[1:]) or "Write a Python function that validates an email address."
    print(asyncio.run(run(task)))
