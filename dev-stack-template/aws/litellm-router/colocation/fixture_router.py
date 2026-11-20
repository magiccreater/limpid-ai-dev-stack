"""Exercise LiteLLM and real Laya with a synthetic, local provider."""
import json
from urllib.request import Request, urlopen

import litellm_service
from routing import LayaRouter, ORDER, QUESTIONS

app = litellm_service.app

def classify(state, _target):
    req = Request("http://laya:8000/decision", method="POST",
                  data=json.dumps({"state": state, "questions": QUESTIONS}).encode(),
                  headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=4) as response:
        body = json.load(response)
    answer = body["answers"]["tier"]
    tier, score = answer["choice"], answer["answer_confidence"]
    if tier not in ORDER or not 0 <= score <= 1:
        return None
    return tier, score

aliases = ("free-ling", "free-nemotron-ultra", "free-nemotron-super")
router = LayaRouter(
    [{"model_name": name, "litellm_params": {"model": f"openai/{name}",
                                             "api_base": "http://127.0.0.1:8080/fixture/v1",
                                             "api_key": "synthetic"}} for name in aliases],
    "same-host", classify=classify,
)
litellm_service.get_router = lambda: router
litellm_service.reserve = lambda: True  # No production traffic or external API in this fixture.

@app.post("/fixture/v1/chat/completions")
async def fixture(body: dict):
    common = {"id": "synthetic", "created": 1, "model": body["model"]}
    if body.get("stream"):
        from fastapi.responses import StreamingResponse
        async def events():
            yield "data: " + json.dumps({**common, "object": "chat.completion.chunk", "choices": [
                {"index": 0, "delta": {"role": "assistant", "content": "READY"}, "finish_reason": None}
            ]}) + "\n\n"
            yield "data: " + json.dumps({**common, "object": "chat.completion.chunk", "choices": [
                {"index": 0, "delta": {}, "finish_reason": "stop"}
            ]}) + "\n\ndata: [DONE]\n\n"
        return StreamingResponse(events(), media_type="text/event-stream")
    return {**common, "object": "chat.completion", "choices": [
        {"index": 0, "message": {"role": "assistant", "content": "READY"}, "finish_reason": "stop"}
    ]}
