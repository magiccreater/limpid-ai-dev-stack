import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch

try:
    import litellm
    import httpx
    import fastapi
except ImportError:
    litellm = None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "aws/litellm-router"))
if litellm:
    import routing
    import litellm_service as service


@unittest.skipUnless(litellm, "run with the pinned LiteLLM runtime")
class LiteLLMLayaTest(unittest.IsolatedAsyncioTestCase):
    def test_approved_pool_uses_zero_price_guard_and_omits_unapproved_accounts(self):
        models = routing.load_free_models(ROOT / "litellm_config.yaml", {"openrouter": "test-key"})
        self.assertTrue(models)
        for model in models:
            params = model["litellm_params"]
            self.assertTrue(model["model_name"].startswith("free-"))
            self.assertEqual(params["extra_body"]["provider"]["max_price"],
                             {"prompt": 0, "completion": 0, "request": 0})
            self.assertTrue(params["extra_body"]["provider"]["require_parameters"])
        self.assertNotIn("free-groq-llama-70b", {model["model_name"] for model in models})
        groq = routing.load_free_models(ROOT / "litellm_config.yaml", {"groq": "test-key"})
        self.assertIn("free-groq-llama-70b", {m["model_name"] for m in groq})

    async def test_litellm_invokes_laya_and_uses_its_score_to_select_a_model(self):
        models = routing.load_free_models(ROOT / "litellm_config.yaml", {"openrouter": "test-key"})
        engine = routing.LayaRouter(models, "test-function")
        decision = {"model": "laya-typed-decisions",
                    "answers": {"tier": {"choice": "deep", "answer_confidence": 0.91}}}
        chat_reply = litellm.ModelResponse(
            model="synthetic", choices=[{"index": 0, "finish_reason": "stop",
                                         "message": {"role": "assistant", "content": "Done."}}],
        )
        with patch.object(routing, "aws") as aws, patch.object(
            service, "reserve", return_value=True
        ), patch.object(service, "get_router", return_value=engine), patch.object(
            engine, "acompletion", new_callable=AsyncMock, return_value=chat_reply
        ) as completion:
            aws.return_value.invoke.return_value = {"Payload": io.BytesIO(json.dumps(decision).encode())}
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=service.app),
                                         base_url="http://localhost") as client:
                request = {"model": "private-coder-public",
                           "messages": [{"role": "user", "content": "Fix customer-example."}]}
                result = await client.post("/v1/chat/completions", json=request)
                self.assertEqual(result.status_code, 200, result.text)
                self.assertEqual(result.headers["x-limpid-decision"], "laya")
                self.assertEqual(result.headers["x-limpid-route"], "free-nemotron-ultra")
                self.assertEqual(result.headers["x-limpid-decision-score"], "0.910")
                completion.assert_awaited_once()
                self.assertEqual(completion.await_args.kwargs["model"], "free-nemotron-ultra")
                score_request = json.loads(aws.return_value.invoke.call_args.kwargs["Payload"])
                self.assertNotIn("customer-example", json.dumps(score_request))
                self.assertIn("bugfix", score_request["state"])
                aws.assert_called_once_with("lambda")

    async def test_private_requests_are_refused_before_accounting_or_inference(self):
        with patch.object(service, "reserve") as reserve, patch.object(service, "get_router") as router:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=service.app),
                                         base_url="http://localhost") as client:
                result = await client.post("/v1/chat/completions", json={"model": "private-coder"})
            self.assertEqual(result.status_code, 503)
            reserve.assert_not_called()
            router.assert_not_called()

    async def test_unavailable_laya_and_first_provider_use_free_fallback(self):
        models = routing.load_free_models(ROOT / "litellm_config.yaml", {"openrouter": "test-key"})
        engine = routing.LayaRouter(models, "test-function", classify=lambda *_: None)
        with patch.object(engine, "acompletion", new_callable=AsyncMock,
                          side_effect=[RuntimeError("rate limit"), "fallback answer"]) as api:
            result = await engine.public_completion({"model": "private-coder-public", "messages": [
                {"role": "user", "content": "Fix a small bug."}
            ]})
        self.assertEqual(result, ("fallback answer", routing.FREE_FALLBACK, "rules", None))
        self.assertEqual([call.kwargs["model"] for call in api.await_args_list],
                         ["free-ling", routing.FREE_FALLBACK])


    async def test_explicit_public_pool_can_choose_groq_while_openrouter_scope_stays_on_openrouter(self):
        models = routing.load_free_models(ROOT / "litellm_config.yaml", {"openrouter": "a", "groq": "b"})
        engine = routing.LayaRouter(models, "test-function", classify=lambda *_: ("quick", 0.9))
        messages = [{"role": "user", "content": "Fix a small test."}]
        with patch.object(engine, "acompletion", new_callable=AsyncMock, return_value="answer") as api:
            await engine.public_completion({"model": "private-coder-public", "messages": messages})
            await engine.public_completion({"model": "public-free-coder", "messages": messages})
        self.assertEqual([call.kwargs["model"] for call in api.await_args_list],
                         ["free-ling", "free-groq-llama-70b"])
