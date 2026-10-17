"""
Stock / Signals Agent — educational research only.

WARNING: Not financial advice. Comply with local regulations before selling signals.
Uses yfinance for market data + LLM for narrative summary.
"""

from __future__ import annotations

import asyncio
import sys

from devstack_shared.llm import get_llm


def fetch_basic(ticker: str) -> dict:
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        info = t.info or {}
        hist = t.history(period="1mo")
        last = float(hist["Close"].iloc[-1]) if not hist.empty else None
        return {
            "symbol": ticker.upper(),
            "name": info.get("shortName") or info.get("longName"),
            "sector": info.get("sector"),
            "last_close": last,
            "currency": info.get("currency"),
            "summary": (info.get("longBusinessSummary") or "")[:800],
        }
    except Exception as e:
        return {"symbol": ticker.upper(), "error": str(e)}


async def analyze(ticker: str) -> str:
    data = fetch_basic(ticker)
    llm = get_llm(tier="private")
    prompt = f"""You are a careful equity research assistant.
This is educational only — never give buy/sell advice framed as guaranteed.

Data:
{data}

Write a short research note:
- What the company does
- Recent price context (1 month)
- Key risks
- Questions an investor should investigate further
End with: "This is not financial advice."
"""
    res = await llm.ainvoke(prompt)
    return res.content


if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    print(asyncio.run(analyze(ticker)))
