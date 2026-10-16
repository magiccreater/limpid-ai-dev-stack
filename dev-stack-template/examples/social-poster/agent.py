"""
Social Media Poster Agent — draft platform-specific posts.

Usage:
  uv run python agent.py "Launch of our new AI study planner for students"
"""

from __future__ import annotations

import asyncio
import sys

from devstack_shared.llm import get_llm


PLATFORMS = ["twitter", "linkedin", "instagram"]


async def draft_posts(topic: str) -> dict[str, str]:
    llm = get_llm(tier="hybrid")
    prompt = f"""You are a social media strategist.
Topic: {topic}

Write one short post for each platform:
- twitter: max 260 chars, punchy, 1-2 hashtags
- linkedin: professional, 2-4 short paragraphs, soft CTA
- instagram: visual-first caption + 5 hashtags

Return JSON with keys: twitter, linkedin, instagram. No markdown fences.
"""
    res = await llm.ainvoke(prompt)
    import json
    try:
        return json.loads(res.content)
    except Exception:
        return {"raw": res.content}


if __name__ == "__main__":
    topic = " ".join(sys.argv[1:]) or "Our new local AI coding stack"
    posts = asyncio.run(draft_posts(topic))
    for k, v in posts.items():
        print(f"\n=== {k.upper()} ===\n{v}\n")
