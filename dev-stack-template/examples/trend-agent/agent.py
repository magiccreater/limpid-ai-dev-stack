"""
Trending / Research Agent — digests current topics.

For production: plug SerpAPI / X API / RSS.
This starter uses the LLM knowledge + optional web search later.
"""

from __future__ import annotations

import asyncio
import sys

from devstack_shared.llm import get_llm


async def trend_digest(topic: str, audience: str = "developers") -> str:
    llm = get_llm(tier="open")  # public trends only: OpenRouter (zero data retention). Use "private" for anything sensitive.
    prompt = f"""You are a research analyst.
Topic: {topic}
Audience: {audience}

Produce a concise trend digest with:
1. Why it matters now (2-3 sentences)
2. 5 concrete signals / developments
3. Opportunities for builders or businesses
4. Risks or open questions
Keep it under 400 words.
"""
    res = await llm.ainvoke(prompt)
    return res.content


if __name__ == "__main__":
    topic = " ".join(sys.argv[1:]) or "local AI agents and personal assistants 2026"
    print(asyncio.run(trend_digest(topic)))
