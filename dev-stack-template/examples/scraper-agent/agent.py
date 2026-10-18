"""
Web Scraping Agent — structured extraction with Playwright.

Install:
  uv sync
  playwright install chromium

Usage:
  uv run python agent.py https://example.com "Extract all product names and prices"
"""

from __future__ import annotations

import asyncio
import json
import sys

from devstack_shared.llm import get_llm


async def scrape_and_extract(url: str, instruction: str) -> dict:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        text = await page.inner_text("body")
        await browser.close()

    # Truncate very long pages
    text = text[:12000]

    llm = get_llm(tier="private")
    prompt = f"""You are a precise data extraction agent.
URL: {url}
Instruction: {instruction}

Page text:
{text}

Return ONLY valid JSON with the extracted fields. No markdown.
"""
    res = await llm.ainvoke(prompt)
    try:
        return json.loads(res.content)
    except json.JSONDecodeError:
        return {"raw": res.content}


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    instruction = " ".join(sys.argv[2:]) or "Summarize the main content in 3 bullets"
    result = asyncio.run(scrape_and_extract(url, instruction))
    print(json.dumps(result, indent=2, ensure_ascii=False))
