"""IAM-invoked Laya decision service. Requests and answers stay out of logs."""

from datetime import datetime, timezone
from functools import lru_cache
import json
import os
import re

from fetch_model import CHECKPOINT, ROOT

MODEL = "laya-typed-decisions"
MAX_BYTES = 32 * 1024
MAX_STATE = 8_000
QUESTION_ID = re.compile(r"[a-z][a-z0-9_]{0,63}")


def validate(event):
    if not isinstance(event, dict) or set(event) - {"state", "questions", "model"}:
        raise ValueError("Expected a decision request with state and questions.")
    if event.get("model") not in (None, MODEL):
        raise ValueError("Unsupported model.")
    if len(json.dumps(event, ensure_ascii=False).encode()) > MAX_BYTES:
        raise ValueError("Decision payload exceeds 32 KiB.")
    state = event.get("state")
    questions = event.get("questions")
    if not isinstance(state, str) or not state.strip() or len(state) > MAX_STATE:
        raise ValueError("State must be 1 to 8,000 characters of text.")
    if not isinstance(questions, dict) or not 1 <= len(questions) <= 8:
        raise ValueError("Supply one to eight typed questions.")
    for key, spec in questions.items():
        if (not QUESTION_ID.fullmatch(key) or not isinstance(spec, dict)
                or set(spec) - {"type", "instructions", "criteria"}):
            raise ValueError("Invalid decision question.")
        kind = spec.get("type")
        if kind not in ("noul", "choice", "score"):
            raise ValueError("Supported decision types are noul, choice and score.")
        if not isinstance(spec.get("instructions"), str) or not 0 < len(spec["instructions"]) <= 1_000:
            raise ValueError("Question instructions must be 1 to 1,000 characters.")
        criteria = spec.get("criteria")
        if kind == "noul" and criteria is None:
            continue
        if (not isinstance(criteria, dict) or not 2 <= len(criteria) <= 12
                or not all(isinstance(value, str) and len(value) <= 500 for value in criteria.values())):
            raise ValueError("Criteria must describe two to twelve options.")
    return state, questions


@lru_cache(maxsize=1)
def model():
    import torch
    from laya import Agent

    torch.set_num_threads(2)
    return Agent(str(ROOT / "typed-decisions"), device="cpu")


@lru_cache(maxsize=1)
def dynamodb():
    import boto3
    from botocore.config import Config

    return boto3.client("dynamodb", config=Config(
        connect_timeout=2, read_timeout=3, retries={"total_max_attempts": 1},
    ))


def reserve():
    table = os.getenv("USAGE_TABLE")
    if not table:
        if os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
            raise RuntimeError("Usage table is missing.")
        return True

    from botocore.exceptions import ClientError

    try:
        dynamodb().update_item(
            TableName=table, Key={"month": {"S": datetime.now(timezone.utc).strftime("%Y-%m")}},
            UpdateExpression="ADD calls :one",
            ConditionExpression="attribute_not_exists(calls) OR calls < :limit",
            ExpressionAttributeValues={":one": {"N": "1"}, ":limit": {"N": os.environ["MONTHLY_DECISIONS"]}},
        )
    except ClientError as error:
        if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise
    return True


def handle(event, _context):
    try:
        state, questions = validate(event)
    except (ValueError, TypeError, RecursionError):
        return {"error": "Invalid decision request.", "code": "invalid_request"}

    try:
        if not reserve():
            return {"error": "Monthly Laya decision cap reached.", "code": "quota"}
        prediction = model().predict(state, questions)
        return {"model": MODEL, "revision": CHECKPOINT, "answers": prediction["answers"]}
    except Exception:
        return {"error": "Laya decision service unavailable.", "code": "unavailable"}
