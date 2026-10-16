"""Static checks on the stack's config files and scripts."""

import re
import unittest

import yaml

from tests.helpers import STACK

CONFIG = yaml.safe_load((STACK / "litellm_config.yaml").read_text())
MODELS = {m["model_name"]: m for m in CONFIG["model_list"]}


class LiteLLMConfigTests(unittest.TestCase):
    def test_master_key_comes_from_env(self):
        self.assertEqual(CONFIG["general_settings"]["master_key"], "os.environ/LITELLM_MASTER_KEY")

    def test_hybrid_fallbacks_are_router_level_and_never_paid_frontier(self):
        fallbacks = CONFIG["router_settings"]["fallbacks"]
        chain = next(f["hybrid-agent"] for f in fallbacks if "hybrid-agent" in f)
        self.assertTrue(chain)
        self.assertNotIn("cloud-reasoner", chain)
        for name in chain:
            self.assertIn(name, MODELS)
        for m in CONFIG["model_list"]:
            self.assertNotIn("fallbacks", m, "fallbacks inside a model entry are ignored by LiteLLM")

    def test_every_paid_model_has_prices_so_budgets_work(self):
        for name, m in MODELS.items():
            if m["litellm_params"]["model"].startswith("openrouter/"):
                info = m.get("model_info", {})
                self.assertGreater(info.get("input_cost_per_token", 0), 0, name)
                self.assertGreater(info.get("output_cost_per_token", 0), 0, name)

    def test_openrouter_has_a_budget_and_frontier_has_its_own_cap(self):
        budget = CONFIG["router_settings"]["provider_budget_config"]["openrouter"]
        self.assertGreater(budget["budget_limit"], 0)
        self.assertGreater(MODELS["cloud-reasoner"]["litellm_params"]["max_budget"], 0)

    def test_local_models_use_env_url(self):
        for name in ("local-coder", "hybrid-agent"):
            self.assertEqual(MODELS[name]["litellm_params"]["api_base"], "os.environ/LOCAL_LLM_BASE_URL")


class ExposureTests(unittest.TestCase):
    TEXT_FILES = [p for p in STACK.rglob("*")
                  if p.is_file() and p.suffix in {".sh", ".ps1", ".yaml", ".yml", ".tmpl", ".py", ".example", ""}
                  and "tests" not in p.parts]

    def test_no_service_binds_all_interfaces(self):
        bad = re.compile(r"(--host[ =]+0\.0\.0\.0|\"0\.0\.0\.0:|- \"?[0-9]+:[0-9]+\"?$)", re.M)
        for p in self.TEXT_FILES:
            self.assertIsNone(bad.search(p.read_text(errors="ignore")), p)

    def test_published_key_is_gone(self):
        for p in self.TEXT_FILES:
            text = p.read_text(errors="ignore")
            if p.name in {"devstack_env.py", "llm.py"}:
                continue  # these list it in order to reject it
            self.assertNotIn("sk-dev-proxy-key", text, p)

    def test_docker_images_are_pinned(self):
        for p in (STACK / "docker").glob("*.yml"):
            for image in re.findall(r"image:\s*(\S+)", p.read_text()):
                self.assertNotRegex(image, r"(:latest$|^[^:]+$)", f"{p.name}: {image}")

    def test_docker_ports_bind_localhost(self):
        for p in (STACK / "docker").glob("*.yml"):
            for port in yaml.safe_load(p.read_text())["services"].values():
                for mapping in port.get("ports", []):
                    self.assertTrue(str(mapping).startswith("127.0.0.1:"), f"{p.name}: {mapping}")


if __name__ == "__main__":
    unittest.main()
