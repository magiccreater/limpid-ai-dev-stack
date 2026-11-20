"""Publish the locally verified Laya image to an active AWS Free Plan project."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

REGION = "ap-southeast-2"
STACK = "limpid-laya-decisions"
IMAGE = "limpid-laya-decisions:pilot"
HERE = Path(__file__).resolve().parent
MAX_IMAGE_BYTES = 5 * 1024**3


def run(profile, expected_project):
    env = dict(os.environ, AWS_PAGER="", AWS_MAX_ATTEMPTS="1",
               AWS_IGNORE_CONFIGURED_ENDPOINT_URLS="true", AWS_CLI_AUTO_PROMPT="off")

    def aws(*args, region=REGION, capture=False):
        return subprocess.run(
            ["aws", "--profile", profile, "--region", region, "--output", "json", *args],
            check=True, capture_output=capture, env=env,
        ).stdout

    def require_free_plan():
        state = json.loads(aws("freetier", "get-account-plan-state", region="us-east-1", capture=True))
        if state.get("accountPlanType") != "FREE" or state.get("accountPlanStatus") != "ACTIVE":
            raise ValueError("An active AWS Free Plan is required.")

    identity = json.loads(aws("sts", "get-caller-identity", capture=True))
    if identity["Account"] != expected_project:
        raise ValueError("The WSL AWS profile does not match the selected project.")
    require_free_plan()

    image = json.loads(subprocess.check_output(["docker", "image", "inspect", IMAGE]))[0]
    if not 0 < image["Size"] <= MAX_IMAGE_BYTES or (image["Os"], image["Architecture"]) != ("linux", "amd64"):
        raise ValueError("Expected a locally tested linux/amd64 Laya image under 5 GiB.")

    def deploy(*parameters):
        aws("cloudformation", "deploy", "--stack-name", STACK, "--template-file", str(HERE / "stack.json"),
            "--capabilities", "CAPABILITY_IAM", "--no-fail-on-empty-changeset",
            *(("--parameter-overrides", *parameters) if parameters else ()))

    # Skip bootstrapping when the repository already exists so updates keep serving the old digest.
    repos = json.loads(aws("ecr", "describe-repositories", capture=True))["repositories"]
    if not any(repo["repositoryName"] == STACK for repo in repos):
        deploy()

    registry = f"{expected_project}.dkr.ecr.{REGION}.amazonaws.com"
    tag = "pilot-" + image["Id"].removeprefix("sha256:")[:20]
    remote = f"{registry}/{STACK}:{tag}"
    images = json.loads(aws("ecr", "list-images", "--repository-name", STACK, capture=True))["imageIds"]
    found = next((entry for entry in images if entry.get("imageTag") == tag), None)
    if found is None:
        require_free_plan()
        with tempfile.TemporaryDirectory(prefix="laya-docker-") as config:
            docker = ["docker", "--config", config]
            subprocess.run([*docker, "login", "--username", "AWS", "--password-stdin", registry],
                           input=aws("ecr", "get-login-password", capture=True), check=True)
            subprocess.run([*docker, "tag", IMAGE, remote], check=True)
            subprocess.run([*docker, "push", remote], check=True)

    result = json.loads(aws("ecr", "describe-images", "--repository-name", STACK,
                            "--image-ids", f"imageTag={tag}", capture=True))["imageDetails"][0]
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", result["imageDigest"]):
        raise ValueError("ECR returned an invalid image digest.")
    size = result["imageSizeInBytes"] / 1024**2
    print(f"Private ECR artifact size: {size:.0f} MiB", flush=True)
    require_free_plan()
    deploy(f"ImageDigest={result['imageDigest']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--project", required=True, help="Expected 12-digit AWS project ID")
    args = parser.parse_args()
    try:
        if not re.fullmatch(r"[0-9]{12}", args.project):
            raise ValueError("Expected a 12-digit AWS project ID.")
        run(args.profile, args.project)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        # AWS/Docker commands already report public diagnostics. Do not print captured credentials.
        print(f"Decision deployment failed ({type(error).__name__}).", file=sys.stderr)
        if isinstance(error, ValueError):
            print(str(error), file=sys.stderr)
        sys.exit(1)
