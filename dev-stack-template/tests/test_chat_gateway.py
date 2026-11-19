import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "aws/chat-gateway/infra.py"
SPEC = importlib.util.spec_from_file_location("chat_gateway_infra", PATH)
infra = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(infra)


class GatewayInfrastructure(unittest.TestCase):
    def test_render_inlines_code_and_sets_iam_streaming(self):
        template = infra.render()
        resources = template["Resources"]
        method = resources["ChatPost"]["Properties"]
        self.assertEqual(method["AuthorizationType"], "AWS_IAM")
        self.assertEqual(method["Integration"]["ResponseTransferMode"], "STREAM")
        self.assertIn("qwen.qwen3-coder-next", resources["Gateway"]["Properties"]["Code"]["ZipFile"])
        deployment = resources["Stage"]["Properties"]["DeploymentId"]["Ref"]
        self.assertIn(deployment, resources)
        self.assertNotEqual(deployment, "Deployment")

    def test_zero_applied_quota_blocks_the_free_plan_pilot(self):
        responses = [
            {"Account": "123456789012"},
            {"accountPlanType": "FREE", "accountPlanStatus": "ACTIVE"},
            {"regionAvailability": "AVAILABLE", "authorizationStatus": "AUTHORIZED",
             "entitlementAvailability": "AVAILABLE"},
            {},
            {"Quotas": [{"QuotaName": name, "Value": 0} for name in infra.QUOTAS]},
        ]
        with patch.object(infra, "aws_json", side_effect=responses):
            with self.assertRaisesRegex(RuntimeError, "positive applied request and token quotas"):
                infra.preflight("pilot", "123456789012")
