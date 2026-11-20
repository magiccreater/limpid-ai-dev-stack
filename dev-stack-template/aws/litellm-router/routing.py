"""LiteLLM policy for choosing among verified public free routes."""

import asyncio
from collections import OrderedDict
from functools import lru_cache
import json
import math
from pathlib import Path
import re
import time

import boto3
from botocore.config import Config
import litellm
import yaml

REGION = "ap-southeast-2"
PUBLIC_MODEL = "private-coder-public"
PUBLIC_FREE_MODEL = "public-free-coder"
LAMBDA_MODEL = "laya-typed-decisions"
FREE_FALLBACK = "free-openrouter-auto"
OPENROUTER = "openrouter"
DIRECT = {
    "groq": ("groq/", None, "GROQ_API_KEY"),
    "cerebras": ("cerebras/", None, "CEREBRAS_API_KEY"),
    "github": ("openai/", "https://models.inference.ai.azure.com", "GITHUB_TOKEN"),
    "sambanova": ("openai/", "https://api.sambanova.ai/v1", "SAMBANOVA_API_KEY"),
}
ORDER = {
    "quick": ("free-groq-llama-70b", "free-cerebras-70b", "free-ling", "free-ernie"),
    "deep": ("free-nemotron-ultra", "free-flint", "free-sambanova-405b", "free-github-r1"),
    "review": ("free-nemotron-super", "free-github-llama-70b", "free-gemma-31b", "free-nemotron-ultra"),
}
QUESTIONS = {"tier": {
    "type": "choice",
    "instructions": "Choose the capability for the described public coding task.",
    "criteria": {"quick": "A routine code edit, simple bug fix, or targeted test.",
                 "deep": "A complex investigation, risky cross-cutting change, or architecture decision.",
                 "review": "Review an existing diff for correctness and risks."},
}}
AWS_CONFIG = Config(connect_timeout=1, read_timeout=4, retries={"total_max_attempts": 1})


@lru_cache(maxsize=3)
def aws(service):
    return boto3.client(service, region_name=REGION, config=AWS_CONFIG)


def provider_for(params):
    model = params.get("model", "")
    if model.startswith("openrouter/") and model.endswith(":free") and not params.get("api_base"):
        return OPENROUTER
    for provider, (prefix, base, env) in DIRECT.items():
        if model.startswith(prefix) and params.get("api_base") == base and params.get("api_key") == "os.environ/" + env:
            return provider
    return None


def openrouter_options():
    return {"provider": {"require_parameters": True, "max_price": {"prompt": 0, "completion": 0, "request": 0}}}


def load_free_models(path, keys):
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    models = []
    for item in raw["model_list"]:
        name, params = item["model_name"], item["litellm_params"]
        info = item.get("model_info", {})
        if not name.startswith("free-") or not info.get("supports_function_calling") or any(
            type(info.get(field)) not in (int, float) or info[field] != 0
            for field in ("input_cost_per_token", "output_cost_per_token")
        ):
            continue
        provider = provider_for(params)
        if provider not in keys:
            continue
        # Configuration controls model IDs, while this policy controls destinations, credentials and prices.
        safe = {"model": params["model"], "api_key": keys[provider], "timeout": 15}
        if params.get("api_base"):
            safe["api_base"] = params["api_base"]
        if provider == OPENROUTER:
            safe["extra_body"] = openrouter_options()
        models.append({"model_name": name, "litellm_params": safe, "model_info": dict(info)})
    if keys.get(OPENROUTER):
        models.append({"model_name": FREE_FALLBACK,
                       "litellm_params": {"model": "openrouter/openrouter/free", "api_key": keys[OPENROUTER],
                                          "timeout": 15, "extra_body": openrouter_options()},
                       "model_info": {"supports_function_calling": True,
                                      "input_cost_per_token": 0, "output_cost_per_token": 0}})
    return models


def features(messages):
    # Inspect the first user message in AWS. Send only fixed labels and counts to Laya.
    brief = next((m["content"] for m in messages if m["role"] == "user"), "")
    first_line = brief[:4000].partition("\n")[0].lower()
    if re.search(r"\b(review|audit|second opinion)\b", first_line):
        kind = "review"
    elif re.search(r"\b(migrate|migration|architecture|refactor|concurrency|deadlock|regression across)\b", first_line):
        kind = "complex change"
    elif re.search(r"\b(test|tests|coverage)\b", first_line):
        kind = "test"
    elif re.search(r"\b(fix|bug|debug)\b", first_line):
        kind = "bugfix"
    else:
        kind = "implementation"
    scope = "large" if len(first_line) > 320 else "small"
    return kind, scope


def laya_score(state, function_arn):
    response = aws("lambda").invoke(
        FunctionName=function_arn, InvocationType="RequestResponse",
        Payload=json.dumps({"state": state, "questions": QUESTIONS, "model": LAMBDA_MODEL}).encode(),
    )
    with response["Payload"] as payload:
        if response.get("FunctionError"):
            return None
        data = json.loads(payload.read(32768))
    if data.get("model") != LAMBDA_MODEL:
        return None
    answer = data["answers"]["tier"]
    tier = answer.get("choice")
    scores = answer.get("probabilities") or {}
    score = answer.get("answer_confidence", scores.get(tier))
    if (tier not in ORDER or type(score) not in (int, float) or not math.isfinite(score)
            or not 0 <= score <= 1 or answer.get("abstain") or answer.get("unbound")
            or len(answer.get("prediction_set") or ()) > 1):
        return None
    return tier, score


class LayaRouter(litellm.Router):
    def __init__(self, models, function_arn, classify=laya_score):
        super().__init__(model_list=models, num_retries=0, enable_pre_call_checks=True)
        self.names = tuple(m["model_name"] for m in models)
        self.openrouter_names = tuple(m["model_name"] for m in models
                                      if m["litellm_params"]["model"].startswith("openrouter/"))
        self.function_arn = function_arn
        self.classify = classify
        self.decisions = OrderedDict()
        self.retry_after = 0.0
        self.decision_lock = asyncio.Lock()

    async def choose(self, kind, scope):
        baseline = "review" if kind == "review" else "deep" if scope == "large" or kind == "complex change" else "quick"
        key = (kind, scope)
        async with self.decision_lock:
            now = time.monotonic()
            cached = self.decisions.get(key)
            if cached and cached[0] > now:
                return cached[1]
            if not self.function_arn or now < self.retry_after:
                return baseline, "rules", None
            try:
                state = f"Public coding task type: {kind}\nChange scope: {scope}."
                result = await asyncio.wait_for(asyncio.to_thread(self.classify, state, self.function_arn), timeout=4.5)
            except Exception:
                result = None
            if result is None:
                self.retry_after = time.monotonic() + 45
                return baseline, "rules", None
            tier, score = result
            choice = (tier, "laya", score) if score >= 0.7 else (baseline, "laya-uncertain", score)
            self.decisions[key] = (time.monotonic() + 300, choice)
            return choice

    async def public_completion(self, request):
        names = self.names if request["model"] == PUBLIC_FREE_MODEL else self.openrouter_names
        if not names:
            raise RuntimeError("No free models are available for this scope.")
        tier, decision, score = await self.choose(*features(request["messages"]))
        preferred = [name for name in ORDER[tier] if name in names]
        candidates = preferred[:1]
        if FREE_FALLBACK in names:
            candidates.append(FREE_FALLBACK)
        candidates.extend(name for name in preferred[1:] + list(names) if name not in candidates)
        options = {key: value for key, value in request.items() if key != "model"}
        for name in candidates[:2]:
            try:
                result = await asyncio.wait_for(self.acompletion(model=name, **options), timeout=10)
                return result, name, decision, score
            except Exception:
                continue
        raise RuntimeError("No eligible free model returned a response.")
