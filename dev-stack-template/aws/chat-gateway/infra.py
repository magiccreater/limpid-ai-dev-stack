import argparse
import hashlib
import json
from pathlib import Path
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


def preflight(profile, account):
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
    quotas = {
        q["QuotaName"]: q["Value"]
        for q in get("service-quotas", "list-service-quotas", "--service-code", "bedrock")["Quotas"]
        if q["QuotaName"] in QUOTAS
    }
    for name in sorted(QUOTAS):
        if name in quotas:
            print(f"{name}: {quotas[name]:g}")
    if quotas.keys() != QUOTAS or any(value <= 0 for value in quotas.values()):
        raise RuntimeError("Sydney Qwen3 Coder Next requires positive applied request and token quotas.")
    print("Free Plan, selected model, logging, and applied Sydney quotas verified.")


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
    checks.add_parser("render")
    args = parser.parse_args()
    try:
        if args.operation == "render":
            print(json.dumps(render(), indent=2))
        else:
            preflight(args.profile, args.account_id)
    except (KeyError, OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"chat-gateway: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
