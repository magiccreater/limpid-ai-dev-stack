import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

REGION = "ap-southeast-2"
MODEL = "qwen.qwen3-coder-next"
QUOTAS = {
    "On-demand model inference requests per minute for Qwen3 Coder Next",
    "On-demand model inference tokens per minute for Qwen3 Coder Next",
}
HERE = Path(__file__).resolve().parent


def aws_json(profile, region, *args):
    cmd = ["aws", "--profile", profile, "--region", region, "--output", "json",
           "--no-cli-pager", "--cli-connect-timeout", "5", "--cli-read-timeout", "12", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise RuntimeError(f"AWS {' '.join(args[:2])} failed. Check the project login and permissions.")
    return json.loads(result.stdout) if result.stdout.strip() else {}


def preflight(profile, account, openrouter_parameter=""):
    def get(*args, region=REGION):
        return aws_json(profile, region, *args)

    if get("sts", "get-caller-identity")["Account"] != account:
        raise RuntimeError("AWS profile does not match the expected project.")
    plan = get("freetier", "get-account-plan-state", region="us-east-1")
    if plan["accountPlanType"] != "FREE" or plan["accountPlanStatus"] != "ACTIVE":
        raise RuntimeError("This pilot requires an active AWS Free Plan.")
    availability = get("bedrock", "get-foundation-model-availability", "--model-id", MODEL)
    fields = {
        "regionAvailability": "AVAILABLE",
        "authorizationStatus": "AUTHORIZED",
        "entitlementAvailability": "AVAILABLE",
    }
    if any(availability.get(key) != value for key, value in fields.items()):
        raise RuntimeError("Qwen3 Coder Next must be available and authorized in Sydney.")
    if get("bedrock", "get-model-invocation-logging-configuration").get("loggingConfig"):
        raise RuntimeError("Bedrock invocation logging is enabled in Sydney. The private pilot requires it off.")
    if openrouter_parameter:
        if not re.fullmatch(r"/limpid/chat-gateway/[A-Za-z0-9_-]+", openrouter_parameter):
            raise RuntimeError("Use a parameter named /limpid/chat-gateway/NAME.")
        filters = [{"Key": "Name", "Option": "Equals", "Values": [openrouter_parameter]}]
        parameters = get("ssm", "describe-parameters", "--parameter-filters", json.dumps(filters))["Parameters"]
        expected = {
            "Name": openrouter_parameter,
            "Type": "SecureString",
            "Tier": "Standard",
            "KeyId": "alias/aws/ssm",
        }
        if not any(all(item.get(key) == value for key, value in expected.items()) for item in parameters):
            raise RuntimeError("OpenRouter requires a Sydney Standard SecureString using the AWS managed SSM key.")
        print("OpenRouter free-auto key metadata verified. Fallback requires the public route.")
    quotas = {
        q["QuotaName"]: q["Value"]
        for q in get("service-quotas", "list-service-quotas", "--service-code", "bedrock")["Quotas"]
        if q["QuotaName"] in QUOTAS
    }
    for name in sorted(QUOTAS):
        if name in quotas:
            print(f"{name}: {quotas[name]:g}")
    if quotas.keys() == QUOTAS and all(value > 0 for value in quotas.values()):
        print("Free Plan, selected model, logging, and applied Sydney quotas verified.")
    elif openrouter_parameter:
        print("Sydney Bedrock lacks positive applied quotas. Only the configured public fallback can serve requests.")
    else:
        raise RuntimeError("Sydney Qwen3 Coder Next requires positive applied request and token quotas.")


def render():
    content = (HERE / "gateway.cjs").read_text(encoding="utf-8")
    template = json.loads((HERE / "stack.json").read_text(encoding="utf-8"))
    resources = template["Resources"]
    resources["Gateway"]["Properties"]["Code"]["ZipFile"] = content
    # A new deployment is needed when API Gateway configuration changes.
    api = {name: value for name, value in resources.items()
           if value["Type"] in {"AWS::ApiGateway::RestApi", "AWS::ApiGateway::Resource", "AWS::ApiGateway::Method"}}
    digest = hashlib.sha256(json.dumps(api, sort_keys=True).encode()).hexdigest()[:12]
    deployment = "Deployment" + digest
    resources[deployment] = resources.pop("Deployment")
    resources["Stage"]["Properties"]["DeploymentId"]["Ref"] = deployment
    return template


def main():
    parser = argparse.ArgumentParser()
    checks = parser.add_subparsers(dest="operation", required=True)
    probe = checks.add_parser("preflight")
    probe.add_argument("--profile", required=True)
    probe.add_argument("--account-id", required=True)
    probe.add_argument("--openrouter-parameter", default="")
    checks.add_parser("render")
    args = parser.parse_args()
    try:
        if args.operation == "render":
            print(json.dumps(render(), indent=2))
        else:
            preflight(args.profile, args.account_id, args.openrouter_parameter)
    except (KeyError, OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"chat-gateway: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
