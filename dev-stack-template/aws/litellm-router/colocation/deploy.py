"""Run a bounded, credential-free same-host benchmark on an existing AWS Free Plan."""
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
REGION = "ap-southeast-2"
STACK = "limpid-laya-colocation-test"

def deploy(profile):
    env = dict(os.environ, AWS_PAGER="", AWS_IGNORE_CONFIGURED_ENDPOINT_URLS="true")

    def aws(*args, region=REGION):
        return json.loads(subprocess.check_output(
            ["aws", "--profile", profile, "--region", region, "--output", "json", *args],
            env=env, timeout=30))

    plan = aws("freetier", "get-account-plan-state", region="us-east-1")
    if (plan["accountPlanType"], plan["accountPlanStatus"]) != ("FREE", "ACTIVE"):
        raise SystemExit("An active AWS Free Plan is required.")
    identity = aws("sts", "get-caller-identity")["Account"]
    subnets = aws("ec2", "describe-subnets", "--filters",
                  "Name=default-for-az,Values=true",
                  "Name=availability-zone,Values=ap-southeast-2a")["Subnets"]
    subnet = next(s for s in subnets if s["State"] == "available" and s["MapPublicIpOnLaunch"])
    ami = aws("ssm", "get-parameter", "--name",
              "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64")["Parameter"]["Value"]
    names = ["limpid-laya-decisions", "limpid-litellm-router"]
    images = [aws("lambda", "get-function", "--function-name", name)["Code"]["ResolvedImageUri"] for name in names]
    registry = f"{identity}.dkr.ecr.{REGION}.amazonaws.com"
    for uri, name in zip(images, names):
        if not re.fullmatch(re.escape(f"{registry}/{name}@sha256:") + "[0-9a-f]{64}", uri):
            raise SystemExit("Expected images pinned by digest in the existing Sydney ECR repositories.")
    payloads = "\n".join(
        f"printf %s {base64.b64encode((ROOT/name).read_bytes()).decode()} | base64 -d > /opt/colocation/{name}"
        for name in ("laya_host.py", "fixture_router.py")
    )
    script = f"""#!/bin/bash
set -euo pipefail
shutdown -h +45
dnf install -y docker
systemctl enable --now docker
mkdir -p /opt/colocation
{payloads}
d=$(mktemp -d /run/colocation-auth.XXXXXX)
trap 'rm -r -- "$d"' EXIT
aws ecr get-login-password --region {REGION} | docker --config "$d" login -u AWS --password-stdin {registry}
docker --config "$d" pull {images[0]}
docker --config "$d" pull {images[1]}
docker network create --internal colocated
docker run -d --restart unless-stopped --network colocated --name laya \\
  -v /opt/colocation/laya_host.py:/var/task/laya_host.py:ro --entrypoint python3 {images[0]} laya_host.py
docker run -d --restart unless-stopped --network colocated --name litellm \\
  -p 127.0.0.1:8080:8080 -v /opt/colocation/fixture_router.py:/app/fixture_router.py:ro \\
  --entrypoint python {images[1]} -m uvicorn fixture_router:app --host 0.0.0.0 --port 8080 --no-access-log
"""
    repos = [f"arn:aws:ecr:{REGION}:{identity}:repository/{name}" for name in names]
    policy = lambda action, resource: {"Effect": "Allow", "Action": action, "Resource": resource}
    template = {"AWSTemplateFormatVersion": "2010-09-09", "Resources": {
        "Role": {"Type": "AWS::IAM::Role", "Properties": {
            "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [
                {"Effect": "Allow", "Principal": {"Service": "ec2.amazonaws.com"}, "Action": "sts:AssumeRole"}]},
            "ManagedPolicyArns": ["arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"],
            "Policies": [{"PolicyName": "PullExistingImages", "PolicyDocument": {
                "Version": "2012-10-17", "Statement": [
                    policy("ecr:GetAuthorizationToken", "*"),
                    policy(["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"], repos)
                ]}}]}},
        "Profile": {"Type": "AWS::IAM::InstanceProfile", "Properties": {"Roles": [{"Ref": "Role"}]}},
        "Security": {"Type": "AWS::EC2::SecurityGroup", "Properties": {
            "GroupDescription": "Colocation benchmark with SSM and no inbound connections", "VpcId": subnet["VpcId"],
            "SecurityGroupEgress": [{"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "CidrIp": "0.0.0.0/0"}]}},
        "Host": {"Type": "AWS::EC2::Instance", "Properties": {
            "ImageId": ami, "InstanceType": "m7i-flex.large", "IamInstanceProfile": {"Ref": "Profile"},
            "MetadataOptions": {"HttpTokens": "required", "HttpPutResponseHopLimit": 1},
            "InstanceInitiatedShutdownBehavior": "stop",
            "NetworkInterfaces": [{"DeviceIndex": "0", "SubnetId": subnet["SubnetId"],
                                   "GroupSet": [{"Ref": "Security"}], "AssociatePublicIpAddress": True}],
            "BlockDeviceMappings": [{"DeviceName": "/dev/xvda", "Ebs": {
                "VolumeType": "gp3", "VolumeSize": 16, "Encrypted": True, "DeleteOnTermination": True}}],
            "UserData": base64.b64encode(script.encode()).decode(),
            "Tags": [{"Key": "Name", "Value": STACK}]}}
    }, "Outputs": {"InstanceId": {"Value": {"Ref": "Host"}}}}
    with tempfile.TemporaryDirectory(prefix="colocation-") as folder:
        path = Path(folder) / "stack.json"
        path.write_text(json.dumps(template))
        subprocess.run(["aws", "--profile", profile, "--region", REGION, "cloudformation", "deploy",
                        "--template-file", str(path), "--stack-name", STACK, "--capabilities", "CAPABILITY_IAM",
                        "--no-fail-on-empty-changeset"], env=env, check=True)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    deploy(parser.parse_args().profile)
