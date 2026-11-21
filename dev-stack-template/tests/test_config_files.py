"""Static checks on the stack's config files and scripts."""

from pathlib import Path
import re
import unittest

import yaml

from tests.helpers import STACK

CONFIG = yaml.safe_load((STACK / "litellm_config.yaml").read_text())
MODELS = {m["model_name"]: m for m in CONFIG["model_list"]}


PRIVATE = {n: m for n, m in MODELS.items() if n.startswith("private-")}
ROUTER = CONFIG["router_settings"]
ALIASES = ROUTER.get("model_group_alias", {})
FALLBACKS = {k: v for entry in ROUTER["fallbacks"] for k, v in entry.items()}


def bedrock_model_id(entry: dict) -> str:
    return entry["litellm_params"]["model"].removeprefix("bedrock/converse/")


class LiteLLMConfigTests(unittest.TestCase):
    def test_master_key_comes_from_env(self):
        self.assertEqual(CONFIG["general_settings"]["master_key"], "os.environ/LITELLM_MASTER_KEY")

    def test_private_models_are_bedrock_pinned_to_sydney(self):
        self.assertEqual(set(PRIVATE), {"private-coder", "private-coder-lite", "private-general", "private-reasoner",
                                        "private-glm"})
        for name, m in PRIVATE.items():
            params = m["litellm_params"]
            self.assertTrue(params["model"].startswith("bedrock/converse/"), name)
            self.assertEqual(params["aws_region_name"], "ap-southeast-2", name)
            self.assertNotIn("api_base", params, name)
            self.assertTrue(m["model_info"].get("supports_function_calling"), name)

    def test_private_models_only_fall_back_to_private_models(self):
        for group, chain in FALLBACKS.items():
            target_group = ALIASES.get(group, group)
            if target_group.startswith("private-"):
                for name in chain:
                    self.assertIn(name, PRIVATE, f"{group} falls back to non-private {name}")
        for m in CONFIG["model_list"]:
            self.assertNotIn("fallbacks", m, "fallbacks inside a model entry are ignored by LiteLLM")

    def test_old_names_are_private_aliases_with_their_own_fallbacks(self):
        for old in ("local-coder", "hybrid-agent"):
            self.assertEqual(ALIASES[old], "private-coder")
            self.assertNotIn(old, MODELS)
            self.assertTrue(set(FALLBACKS[old]) <= set(PRIVATE), old)

    def test_frontier_is_never_a_fallback(self):
        for chain in FALLBACKS.values():
            self.assertNotIn("cloud-reasoner", chain)

    def test_openrouter_models_ask_for_zero_data_retention(self):
        for name, m in MODELS.items():
            model = m["litellm_params"]["model"]
            if model.startswith("openrouter/"):
                policy = {"zdr": False, "data_collection": "allow"} if model.endswith(":free") else {"zdr": True}
                self.assertEqual(m["litellm_params"].get("extra_body"), {"provider": policy}, name)

    def test_every_paid_model_has_prices_so_budgets_work(self):
        for name, m in MODELS.items():
            info = m.get("model_info", {})
            if m["litellm_params"]["model"].endswith(":free") or name.startswith("free-"):
                self.assertEqual((info.get("input_cost_per_token"), info.get("output_cost_per_token")), (0, 0), name)
                continue
            self.assertGreater(info.get("input_cost_per_token", 0), 0, name)
            self.assertGreater(info.get("output_cost_per_token", 0), 0, name)

    def test_each_provider_has_a_daily_budget_and_frontier_its_own_cap(self):
        budgets = ROUTER["provider_budget_config"]
        for provider in ("bedrock", "openrouter"):
            self.assertGreater(budgets[provider]["budget_limit"], 0, provider)
        self.assertGreater(MODELS["cloud-reasoner"]["litellm_params"]["max_budget"], 0)

    def test_no_local_model_remains(self):
        text = (STACK / "litellm_config.yaml").read_text()
        self.assertNotIn("LOCAL_LLM_BASE_URL", text)
        self.assertNotIn("openai/local", text)


class AwsPolicyTests(unittest.TestCase):
    TEMPLATE = (STACK / "aws" / "bedrock-access.yaml").read_text()

    def test_policy_allows_exactly_the_configured_private_models_in_sydney(self):
        allowed = set(re.findall(r"arn:aws:bedrock:([a-z0-9-]+)::foundation-model/(\S+)", self.TEMPLATE))
        self.assertEqual({region for region, _ in allowed}, {"ap-southeast-2"})
        self.assertEqual({model for _, model in allowed}, {bedrock_model_id(m) for m in PRIVATE.values()})

    def test_policy_has_no_wildcards_and_only_invoke_actions(self):
        self.assertNotRegex(self.TEMPLATE, r"Resource:\s*['\"]?\*")
        actions = set(re.findall(r"- (bedrock:\w+)", self.TEMPLATE))
        self.assertEqual(actions, {"bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"})

    def test_stack_is_restricted_to_sydney(self):
        self.assertIn('!Equals [!Ref "AWS::Region", ap-southeast-2]', self.TEMPLATE)


class ExposureTests(unittest.TestCase):
    TEXT_FILES = [p for p in STACK.rglob("*")
                  if p.is_file() and p.suffix in {".sh", ".ps1", ".yaml", ".yml", ".tmpl", ".py", ".example", ""}
                  and "tests" not in p.parts]

    def test_no_service_binds_all_interfaces(self):
        bad = re.compile(r"(--host[ =]+0\.0\.0\.0|\"0\.0\.0\.0:|- \"?[0-9]+:[0-9]+\"?$)", re.M)
        for p in self.TEXT_FILES:
            text = p.read_text(errors="ignore")
            match = bad.search(text)
            if match is None:
                continue
            rel_path = p.relative_to(STACK)
            # Narrow allowlist with paired-mapping check:
            # deploy.py:59 runs uvicorn inside a container listening on 0.0.0.0 for Docker forwarding,
            # but host exposure is strictly prevented by loopback mapping (-p 127.0.0.1:8080:8080).
            if rel_path == Path("aws/litellm-router/colocation/deploy.py"):
                if "-p 127.0.0.1:" in text:
                    continue
            self.fail(f"Service binds all interfaces in {rel_path}: {match.group(0)}")

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
