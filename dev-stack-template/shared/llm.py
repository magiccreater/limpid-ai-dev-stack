"""Shared LLM client that talks to LiteLLM (local + OpenRouter hybrid)."""

from __future__ import annotations

import os
from typing import Literal

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

Tier = Literal["local", "open", "hybrid", "frontier"]


def get_llm(tier: Tier = "hybrid", temperature: float = 0.2) -> ChatOpenAI:
    """
    tier:
      - local    → Arc llama.cpp only
      - open     → strong open models on OpenRouter
      - hybrid   → local first, then open, then frontier (via LiteLLM fallbacks)
      - frontier → Claude / strong closed models
    """
    base = os.getenv("LITELLM_BASE_URL", "http://localhost:4000/v1")
    key = os.getenv("LITELLM_MASTER_KEY", "sk-dev-proxy-key")

    model_map = {
        "local": "local-coder",
        "open": "open-deepseek",
        "hybrid": "hybrid-agent",
        "frontier": "cloud-reasoner",
    }
    model = model_map[tier]

    return ChatOpenAI(
        model=model,
        openai_api_base=base,
        openai_api_key=key,
        temperature=temperature,
        max_retries=2,
        timeout=180,
    )


def get_direct_openrouter(model: str = "deepseek/deepseek-chat") -> ChatOpenAI:
    """Bypass LiteLLM when you need a specific OpenRouter model."""
    return ChatOpenAI(
        model=model,
        openai_api_base="https://openrouter.ai/api/v1",
        openai_api_key=os.getenv("OPENROUTER_API_KEY"),
        default_headers={
            "HTTP-Referer": "http://localhost:3000",
            "X-Title": "DevStack",
        },
        temperature=0.2,
    )
