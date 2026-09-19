"""
Mentor / Coaching Agent — long-horizon personal development.

In production, persist memory in OpenClaw or a local SQLite / vector store.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.llm import get_llm


SYSTEM = """You are a thoughtful mentor and coach.
Style: Socratic, practical, kind but direct.
Ask clarifying questions when goals are vague.
Offer one concrete next action at a time.
Remember previous context if provided.
Never be preachy or overly long.
"""


async def coach(user_message: str, history: list[dict] | None = None) -> str:
    llm = get_llm(tier="hybrid")
    messages = [{"role": "system", "content": SYSTEM}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    res = await llm.ainvoke(messages)
    return res.content


if __name__ == "__main__":
    msg = " ".join(sys.argv[1:]) or "I want to become more consistent with deep work."
    print(asyncio.run(coach(msg)))
