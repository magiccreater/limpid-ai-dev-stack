import unittest
from unittest import mock

from devstack_shared import llm


class TierTests(unittest.TestCase):
    def test_frontier_refused_unless_allowed(self):
        with self.assertRaises(llm.FrontierNotAllowed):
            llm.resolve_model("frontier", env={})
        with self.assertRaises(llm.FrontierNotAllowed):
            llm.resolve_model("frontier", env={"ALLOW_FRONTIER": "0"})
        self.assertEqual(llm.resolve_model("frontier", env={"ALLOW_FRONTIER": "1"}), "cloud-reasoner")

    def test_other_tiers_and_unknown(self):
        self.assertEqual(llm.resolve_model("local", env={}), "local-coder")
        self.assertEqual(llm.resolve_model("hybrid", env={}), "hybrid-agent")
        self.assertEqual(llm.resolve_model("open", env={}), "open-deepseek")
        with self.assertRaises(ValueError):
            llm.resolve_model("gpt", env={})

    def test_complexity_mapping_never_escalates_to_paid_frontier_by_default(self):
        cases = [(0, "local"), (1.49, "local"), (1.5, "hybrid"), (2.49, "hybrid"), (3, "open"),
                 (float("nan"), "local"), (float("inf"), "local")]
        for score, tier in cases:
            self.assertEqual(llm.tier_for_complexity(score, env={}), tier, score)
        self.assertEqual(llm.tier_for_complexity(3, env={"ALLOW_FRONTIER": "1"}), "frontier")


class GatewayTests(unittest.TestCase):
    def test_missing_or_published_key_is_refused(self):
        for env in ({}, {"LITELLM_MASTER_KEY": "__GENERATE__"}, {"LITELLM_MASTER_KEY": "sk-dev-proxy-key"}):
            with self.assertRaises(llm.GatewayNotConfigured):
                llm.gateway_settings(env)

    def test_defaults_to_localhost(self):
        base, key = llm.gateway_settings({"LITELLM_MASTER_KEY": "sk-x"})
        self.assertEqual(base, "http://127.0.0.1:4000/v1")
        self.assertEqual(key, "sk-x")

    def test_get_llm_builds_client_for_tier(self):
        env = {"LITELLM_MASTER_KEY": "sk-test", "LITELLM_BASE_URL": "http://127.0.0.1:4999/v1"}
        with mock.patch.dict("os.environ", env, clear=True), mock.patch.object(llm, "load_env"):
            model = llm.get_llm("local")
        self.assertEqual(model.model_name, "local-coder")
        self.assertEqual(str(model.openai_api_base), "http://127.0.0.1:4999/v1")
        self.assertEqual(model.openai_api_key.get_secret_value(), "sk-test")


if __name__ == "__main__":
    unittest.main()
