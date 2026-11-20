"""AWS IAM ingress for a Sydney LiteLLM Router backed by Laya."""

import asyncio
from datetime import datetime, timezone
from functools import lru_cache
import json
import os
from pathlib import Path

from botocore.exceptions import ClientError
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from routing import DIRECT, OPENROUTER, PUBLIC_MODEL, LayaRouter, aws, load_free_models

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
MAX_BYTES = 65536
KEYS = {"model", "messages", "stream", "max_tokens", "max_completion_tokens", "temperature",
        "top_p", "tools", "tool_choice", "stream_options"}


def valid_message(message):
    if not isinstance(message, dict) or message.get("role") not in ("system", "user", "assistant", "tool"):
        return False
    return isinstance(message.get("content"), str) or (
        message["role"] == "assistant" and message.get("content") is None
        and isinstance(message.get("tool_calls"), list)
    )


def validate(body):
    if not isinstance(body, dict) or set(body) - KEYS:
        raise HTTPException(400, "Unsupported chat completion fields.")
    if body.get("model") == "private-coder":
        raise HTTPException(503, "No private inference route is enabled in this Free Plan pilot.")
    if body.get("model") != PUBLIC_MODEL:
        raise HTTPException(400, "Use private-coder-public to authorize public-only inference.")
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages or not all(valid_message(m) for m in messages):
        raise HTTPException(400, "Only text messages and function calls are supported.")
    tools = body.get("tools", [])
    if not isinstance(tools, list) or any(not isinstance(tool, dict) or tool.get("type") != "function"
                                          or not isinstance(tool.get("function"), dict)
                                          or not isinstance(tool["function"].get("name"), str) for tool in tools):
        raise HTTPException(400, "Only function tools are supported.")
    tokens = body.pop("max_completion_tokens", body.get("max_tokens", 2048))
    if type(tokens) is not int or tokens < 1 or type(body.get("stream", False)) is not bool:
        raise HTTPException(400, "Invalid output limit or streaming mode.")
    body["max_tokens"] = min(tokens, 2048)
    return body


def reserve():
    try:
        aws("dynamodb").update_item(
            TableName=os.environ["USAGE_TABLE"],
            Key={"month": {"S": datetime.now(timezone.utc).strftime("%Y-%m")}},
            UpdateExpression="ADD calls :one",
            ConditionExpression="attribute_not_exists(calls) OR calls < :limit",
            ExpressionAttributeValues={":one": {"N": "1"}, ":limit": {"N": os.environ["MONTHLY_REQUESTS"]}},
        )
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def load_keys():
    enabled = {p.strip() for p in os.environ.get("FREE_PROVIDERS", OPENROUTER).split(",")}
    parameters = {OPENROUTER: "/limpid/chat-gateway/openrouter",
                  **{name: f"/limpid/litellm/free/{name}" for name in DIRECT}}
    keys = {}
    for name in enabled & parameters.keys():
        try:
            parameter = aws("ssm").get_parameter(Name=parameters[name], WithDecryption=True)["Parameter"]
        except ClientError:
            continue
        if parameter.get("Type") == "SecureString" and parameter.get("Value"):
            keys[name] = parameter["Value"]
    return keys


@lru_cache(maxsize=1)
def get_router():
    keys = load_keys()
    models = load_free_models(Path(__file__).with_name("litellm_config.yaml"), keys)
    if not models:
        raise RuntimeError("No credentials for approved public free routes.")
    return LayaRouter(models, os.environ["LAYA_FUNCTION_ARN"])


@app.get("/health")
async def health():
    return {"status": "ok"}


async def stream_response(result):
    try:
        async for part in result:
            yield "data: " + part.model_dump_json(exclude_none=True) + "\n\n"
        yield "data: [DONE]\n\n"
    except Exception:
        yield 'data: {"error":{"message":"Provider stream interrupted."}}\n\n'


@app.post("/v1/chat/completions")
async def completions(request: Request):
    data = bytearray()
    async for segment in request.stream():
        if len(data) + len(segment) > MAX_BYTES:
            raise HTTPException(413, "Request exceeds 64 KiB.")
        data.extend(segment)
    try:
        body = validate(json.loads(data))
    except (ValueError, RecursionError) as exc:
        raise HTTPException(400, "Invalid JSON body.") from exc
    try:
        permitted = await asyncio.to_thread(reserve)
    except Exception as exc:
        raise HTTPException(503, "Gateway usage accounting unavailable.") from exc
    if not permitted:
        raise HTTPException(429, "Monthly gateway request limit reached.")
    try:
        router = await asyncio.to_thread(get_router)
        result, route, decision, score = await router.public_completion(body)
    except Exception as exc:
        raise HTTPException(502, "No approved free model produced a response.") from exc
    headers = {"Cache-Control": "no-store", "X-Limpid-Route": route, "X-Limpid-Decision": decision}
    if score is not None:
        headers["X-Limpid-Decision-Score"] = f"{score:.3f}"
    if body.get("stream"):
        return StreamingResponse(stream_response(result), media_type="text/event-stream", headers=headers)
    return JSONResponse(content=result.model_dump(exclude_none=True), headers=headers)
