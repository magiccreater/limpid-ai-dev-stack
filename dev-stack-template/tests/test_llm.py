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

    def test_tiers_map_to_gateway_model_names(self):
        self.assertEqual(llm.resolve_model("private", env={}), "private-coder")
        self.assertEqual(llm.resolve_model("private-general", env={}), "private-general")
        self.assertEqual(llm.resolve_model("private-reasoner", env={}), "private-reasoner")
        self.assertEqual(llm.resolve_model("open", env={}), "open-deepseek")
        with self.assertRaises(ValueError):
            llm.resolve_model("gpt", env={})

    def test_old_local_and_hybrid_tiers_now_mean_private(self):
        for old in ("local", "hybrid"):
            self.assertEqual(llm.resolve_model(old, env={}), "private-coder")

    def test_every_tier_model_exists_in_the_gateway_config(self):
        import yaml
        from tests.helpers import STACK
        config = yaml.safe_load((STACK / "litellm_config.yaml").read_text())
        names = {m["model_name"] for m in config["model_list"]}
        self.assertTrue(set(llm.TIERS.values()) <= names)

    def test_complexity_mapping_stays_private_unless_frontier_allowed(self):
        cases = [(0, "private"), (1.99, "private"), (2.0, "private-reasoner"), (3, "private-reasoner"),
                 (float("nan"), "private"), (float("inf"), "private")]
        for score, tier in cases:
            self.assertEqual(llm.tier_for_complexity(score, env={}), tier, score)
            self.assertIn(tier, llm.PRIVATE_TIERS)
        allowed = {"ALLOW_FRONTIER": "1"}
        self.assertEqual(llm.tier_for_complexity(2.2, env=allowed), "private-reasoner")
        self.assertEqual(llm.tier_for_complexity(3, env=allowed), "frontier")


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
            model = llm.get_llm()
        self.assertEqual(model.model_name, "private-coder")
        self.assertEqual(str(model.openai_api_base), "http://127.0.0.1:4999/v1")
        self.assertEqual(model.openai_api_key.get_secret_value(), "sk-test")


if __name__ == "__main__":
    unittest.main()
