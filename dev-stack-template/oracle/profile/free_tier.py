"""Require an explicitly free, non-upgraded subscription and the tenancy home region."""
import configparser
import json
from pathlib import Path
import subprocess
import sys


def check(subscriptions, regions, selected):
    active = [s for s in subscriptions if s.get("lifecycle-state") == "ACTIVE"]
    if not active or any(s.get("payment-model") != "FREE_TRIAL" for s in active):
        raise ValueError("Free-only subscription could not be confirmed. Provisioning stopped.")
    if not any(r.get("is-home-region") and r.get("region-name") == selected for r in regions):
        raise ValueError("Use the tenancy home region for the Always Free A1 deployment.")


def records(*args):
    response = subprocess.check_output(["oci", *args, "--all"])
    data = json.loads(response)["data"]
    return data["items"] if isinstance(data, dict) else data


if __name__ == "__main__":
    try:
        config = configparser.ConfigParser(interpolation=None)
        config.read(Path.home() / ".oci/config")
        profile = config["DEFAULT"]
        check(records("organizations", "subscription", "list", "-c", profile["tenancy"]),
              records("iam", "region-subscription", "list"), profile["region"])
    except (ValueError, KeyError, subprocess.CalledProcessError, OSError) as error:
        sys.exit("Free-tier preflight: " + str(error))
