"""
Coding helper: routes a coding question to the cheapest model tier that fits, then
answers it. It returns text (a plan, explanation or code); it does not edit files or
run tests. For real changes in a repo, use Claude Code, Cline or Aider.

Usage:
  just agent coding "Add a health-check endpoint to the FastAPI app"
"""

from __future__ import annotations

import asyncio
import sys

from devstack_shared.jev_client import route_request
from devstack_shared.llm import get_llm, tier_for_complexity

SYSTEM = """You are an expert software engineer.
Prefer small, correct diffs. Explain trade-offs briefly.
When the task is large, break it into ordered steps first.
"""


async def run(task: str) -> str:
    decision = await route_request(task)
    tier = tier_for_complexity(decision.complexity)
    print(
        f"[route] {decision.route} complexity={decision.complexity:.2f} "
        f"source={decision.source} tier={tier}",
        file=sys.stderr,
    )

    llm = get_llm(tier=tier)
    res = await llm.ainvoke([
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": task},
    ])
    return res.content


if __name__ == "__main__":
    task = " ".join(sys.argv[1:]) or "Write a Python function that validates an email address."
    print(asyncio.run(run(task)))
