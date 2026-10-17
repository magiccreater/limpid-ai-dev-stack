"""Chat models through the LiteLLM gateway (see litellm_config.yaml)."""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from typing import TYPE_CHECKING, Literal

from .config import load_env

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

Tier = Literal["private", "private-general", "private-reasoner", "open", "frontier", "local", "hybrid"]

# Tier -> LiteLLM model name. Private tiers run on Amazon Bedrock in Sydney and never
# fall back to OpenRouter; "open" and "frontier" go to OpenRouter (non-sensitive only).
TIERS: dict[str, str] = {
    "private": "private-coder",              # default: coding and agent work
    "private-general": "private-general",    # writing, summaries, general questions
    "private-reasoner": "private-reasoner",  # harder reasoning
    "open": "open-deepseek",                 # cheap, OpenRouter, zero data retention
    "frontier": "cloud-reasoner",            # Claude via OpenRouter: needs ALLOW_FRONTIER=1
}
# Names from earlier versions (the local llama-server is gone; both now mean private).
DEPRECATED_TIERS: dict[str, str] = {"local": "private", "hybrid": "private"}

PRIVATE_TIERS = frozenset(t for t in TIERS if t.startswith("private"))

PUBLISHED_KEYS = {"sk-dev-proxy-key"}


class FrontierNotAllowed(RuntimeError):
    """Raised when code asks for the paid frontier tier without ALLOW_FRONTIER=1."""


class GatewayNotConfigured(RuntimeError):
    """Raised when the LiteLLM key is missing or a published default."""


def frontier_allowed(env: Mapping[str, str] | None = None) -> bool:
    if env is None:
        load_env()
        env = os.environ
    return env.get("ALLOW_FRONTIER", "0").strip() == "1"


def resolve_model(tier: str, env: Mapping[str, str] | None = None) -> str:
    """LiteLLM model name for a tier. Refuses the frontier tier unless allowed."""
    tier = DEPRECATED_TIERS.get(tier, tier)
    if tier not in TIERS:
        raise ValueError(f"unknown tier {tier!r}; use one of {', '.join(TIERS)}")
    if tier == "frontier" and not frontier_allowed(env):
        raise FrontierNotAllowed(
            "the frontier tier calls paid Claude via OpenRouter; set ALLOW_FRONTIER=1 in .env "
            "to allow it, or use your Claude subscription in Claude Code instead"
        )
    return TIERS[tier]


def tier_for_complexity(complexity: float, env: Mapping[str, str] | None = None) -> str:
    """Map a 0-3 complexity score to a tier. Stays private unless frontier is allowed."""
    if not isinstance(complexity, (int, float)) or not math.isfinite(complexity):
        complexity = 1.0
    if complexity < 2.0:
        return "private"
    if complexity >= 2.5 and frontier_allowed(env):
        return "frontier"
    return "private-reasoner"


def gateway_settings(env: Mapping[str, str] | None = None) -> tuple[str, str]:
    """(base_url, key) for LiteLLM. Raises if the key is missing or a published default."""
    env = os.environ if env is None else env
    base = env.get("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
    key = env.get("LITELLM_MASTER_KEY", "")
    if not key or key == "__GENERATE__":
        raise GatewayNotConfigured("LITELLM_MASTER_KEY is not set; run: just env")
    if key in PUBLISHED_KEYS:
        raise GatewayNotConfigured("LITELLM_MASTER_KEY is the published default; run: just env")
    return base, key


def get_llm(tier: Tier = "private", temperature: float = 0.2) -> ChatOpenAI:
    """A LangChain chat model for the given tier, routed through LiteLLM."""
    from langchain_openai import ChatOpenAI

    load_env()
    model = resolve_model(tier)
    base, key = gateway_settings()
    return ChatOpenAI(
        model=model,
        base_url=base,
        api_key=key,
        temperature=temperature,
        max_retries=1,      # LiteLLM already retries and falls back
        timeout=600,        # long agent prompts can take a while
    )
