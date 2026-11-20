"""Build and deploy the opt-in Sydney LiteLLM pilot from WSL."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
STACK = "limpid-litellm-router"
IMAGE = STACK + ":pilot"
REGION = "ap-southeast-2"
PROVIDERS = ("openrouter", "groq", "github", "cerebras", "sambanova")


def build():
    with tempfile.TemporaryDirectory(prefix="litellm-build-") as folder:
        context = Path(folder)
        for name in ("Dockerfile", "requirements.txt", "litellm_service.py", "routing.py"):
            shutil.copy2(HERE / name, context / name)
        shutil.copy2(HERE.parents[1] / "litellm_config.yaml", context / "litellm_config.yaml")
        subprocess.run(["docker", "build", "--platform", "linux/amd64", "-t", IMAGE, str(context)], check=True)


def deploy(profile, project, providers):
    if not re.fullmatch(r"[0-9]{12}", project) or not providers or set(providers) - set(PROVIDERS):
        raise ValueError("Specify a project ID and the approved free-provider names.")
    env = dict(os.environ, AWS_PAGER="", AWS_MAX_ATTEMPTS="1", AWS_CLI_AUTO_PROMPT="off",
               AWS_IGNORE_CONFIGURED_ENDPOINT_URLS="true")

    def aws(*args, region=REGION, output=True):
        return subprocess.run(["aws", "--profile", profile, "--region", region, "--output", "json", *args],
                              env=env, check=True, capture_output=output).stdout

    def call(*args, **kwargs):
        return json.loads(aws(*args, **kwargs))

    def check_plan():
        result = call("freetier", "get-account-plan-state", region="us-east-1")
        if (result.get("accountPlanType"), result.get("accountPlanStatus")) != ("FREE", "ACTIVE"):
            raise ValueError("An active AWS Free Plan is required.")

    if call("sts", "get-caller-identity")["Account"] != project:
        raise ValueError("AWS login is for a different project.")
    check_plan()
    if call("lambda", "get-function-configuration", "--function-name", "limpid-laya-decisions")["State"] != "Active":
        raise ValueError("The Sydney Laya function is unavailable.")
    current = call("cloudformation", "describe-stacks", "--stack-name", "limpid-chat-gateway")["Stacks"][0]
    cap = next(x["ParameterValue"] for x in current["Parameters"] if x["ParameterKey"] == "MonthlyRequests")
    usage = call("cloudformation", "describe-stack-resource", "--stack-name", "limpid-chat-gateway",
                 "--logical-resource-id", "Usage")["StackResourceDetail"]["PhysicalResourceId"]

    image = json.loads(subprocess.check_output(["docker", "image", "inspect", IMAGE]))[0]
    if (image["Os"], image["Architecture"]) != ("linux", "amd64") or image["Size"] > 2 * 1024**3:
        raise ValueError("Build and verify the linux/amd64 pilot image under 2 GiB first.")

    def apply(*extra):
        aws("cloudformation", "deploy", "--stack-name", STACK, "--template-file", str(HERE / "stack.json"),
            "--capabilities", "CAPABILITY_IAM", "--no-fail-on-empty-changeset", "--parameter-overrides",
            f"UsageTable={usage}", f"MonthlyRequests={cap}", f"FreeProviders={','.join(providers)}", *extra, output=False)

    names = call("ecr", "describe-repositories")["repositories"]
    if not any(repo["repositoryName"] == STACK for repo in names):
        apply()
    registry = f"{project}.dkr.ecr.{REGION}.amazonaws.com"
    tag = "pilot-" + image["Id"].split(":")[-1][:20]
    remote = f"{registry}/{STACK}:{tag}"
    tags = call("ecr", "list-images", "--repository-name", STACK)["imageIds"]
    if not any(item.get("imageTag") == tag for item in tags):
        check_plan()
        with tempfile.TemporaryDirectory(prefix="litellm-docker-") as config:
            docker = ["docker", "--config", config]
            subprocess.run([*docker, "login", "--username", "AWS", "--password-stdin", registry],
                           input=aws("ecr", "get-login-password"), check=True)
            subprocess.run([*docker, "tag", IMAGE, remote], check=True)
            subprocess.run([*docker, "push", remote], check=True)
    detail = call("ecr", "describe-images", "--repository-name", STACK, "--image-ids", f"imageTag={tag}")["imageDetails"][0]
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", detail["imageDigest"]):
        raise ValueError("Invalid ECR digest.")
    print(f"Private LiteLLM image: {detail['imageSizeInBytes'] / 1024**2:.0f} MiB", flush=True)
    check_plan()
    apply(f"ImageDigest={detail['imageDigest']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("build", help="build from the repository's tracked LiteLLM configuration")
    apply = commands.add_parser("deploy")
    apply.add_argument("--profile", required=True)
    apply.add_argument("--project", required=True)
    apply.add_argument("--free-providers", default="openrouter")
    args = parser.parse_args()
    try:
        if args.command == "build":
            build()
        else:
            deploy(args.profile, args.project, args.free_providers.split(","))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        # Captured subprocess output may contain registry credentials.
        parser.exit(1, str(error) + "\n" if isinstance(error, ValueError)
                    else f"LiteLLM {args.command} failed. Check the AWS stack events or Docker output.\n")
