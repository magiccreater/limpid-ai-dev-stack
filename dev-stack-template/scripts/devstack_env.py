#!/usr/bin/env python3
"""Manage the dev stack's .env file and render client configs from it.

Standard library only, so it runs before any project dependencies exist.

  python3 scripts/devstack_env.py init   [--env .env] [--example .env.example]
  python3 scripts/devstack_env.py check  [--env .env]
  python3 scripts/devstack_env.py render TEMPLATE OUTPUT [--env .env] [--force]

init    Create .env from .env.example, generating every value marked __GENERATE__.
        On an existing .env: add keys that are missing, generate values still marked
        __GENERATE__, and replace the old published defaults that are safe to rotate.
        Never removes or changes anything else. Sets the file mode to 600.
check   Exit 1 if the LiteLLM key is missing or a known published default.
render  Replace ${VAR} in TEMPLATE with values from .env and write OUTPUT.
        An existing, different OUTPUT is kept and the new version is written next to
        it as OUTPUT.dev-stack-new, unless --force is given or OUTPUT still holds the
        old published LiteLLM key (then it is backed up and replaced).
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
import sys
from pathlib import Path

PLACEHOLDER = "__GENERATE__"

# Values that shipped in earlier versions of this repo, so anyone can know them.
PUBLISHED_DEFAULTS = {
    "LITELLM_MASTER_KEY": {"sk-dev-proxy-key"},
    "ANYTHINGLLM_JWT_SECRET": {"change-me", "change-me-in-production"},
    "MYSQL_ROOT_PASSWORD": {"rootpassword"},
    "MYSQL_PASSWORD": {"dev_password"},
}

# Safe to replace automatically. MySQL passwords are not: the database keeps the
# password it was created with, so changing .env alone would lock you out.
ROTATE_AUTOMATICALLY = {"LITELLM_MASTER_KEY", "ANYTHINGLLM_JWT_SECRET"}

LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")
VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def generate(key: str) -> str:
    if key == "LITELLM_MASTER_KEY":
        return "sk-" + secrets.token_urlsafe(32)
    # Alphanumeric only, so the value is safe in YAML, JSON, shells and URLs.
    return secrets.token_hex(24)


def unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = LINE.match(line)
        if m:
            values[m.group(1)] = unquote(m.group(2))
    return values


def write_private(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def init(env_path: Path, example_path: Path) -> list[str]:
    """Create or upgrade .env. Returns human-readable notes about what changed."""
    notes: list[str] = []
    example = example_path.read_text(encoding="utf-8")

    if not env_path.exists():
        out = []
        for line in example.splitlines():
            m = LINE.match(line)
            if m and not line.lstrip().startswith("#") and unquote(m.group(2)) == PLACEHOLDER:
                out.append(f"{m.group(1)}={generate(m.group(1))}")
            else:
                out.append(line)
        write_private(env_path, "\n".join(out) + "\n")
        notes.append(f"created {env_path} with generated secrets")
        return notes

    lines = env_path.read_text(encoding="utf-8").splitlines()
    present: set[str] = set()
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            continue
        m = LINE.match(line)
        if not m:
            continue
        key, value = m.group(1), unquote(m.group(2))
        present.add(key)
        if value == PLACEHOLDER:
            lines[i] = f"{key}={generate(key)}"
            notes.append(f"generated {key}")
        elif value in PUBLISHED_DEFAULTS.get(key, set()):
            if key in ROTATE_AUTOMATICALLY:
                lines[i] = f"{key}={generate(key)}"
                notes.append(f"replaced the published default {key} with a random value")
                if key == "LITELLM_MASTER_KEY":
                    notes.append(
                        "the LiteLLM key changed: run 'just client-configs', and update the key in "
                        "clients you set up by hand (Cline, AnythingLLM)"
                    )
            else:
                notes.append(
                    f"WARNING: {key} is still the published default. Change it in MySQL "
                    f"first (ALTER USER ...), then in .env."
                )

    added = []
    for key, value in parse(example).items():
        if key not in present:
            added.append(f"{key}={generate(key) if value == PLACEHOLDER else value}")
            notes.append(f"added missing {key}")
    if added:
        lines += ["", "# Added by devstack_env.py init"] + added

    write_private(env_path, "\n".join(lines) + "\n")
    return notes


def check(env_path: Path) -> list[str]:
    if not env_path.exists():
        return [f"{env_path} does not exist; run: just env"]
    values = parse(env_path.read_text(encoding="utf-8"))
    problems = []
    key = values.get("LITELLM_MASTER_KEY", "")
    if not key or key == PLACEHOLDER:
        problems.append("LITELLM_MASTER_KEY is not set; run: just env")
    elif key in PUBLISHED_DEFAULTS["LITELLM_MASTER_KEY"]:
        problems.append("LITELLM_MASTER_KEY is the published default; run: just env")
    return problems


def render(template: Path, output: Path, env_path: Path, force: bool = False) -> str:
    values = parse(env_path.read_text(encoding="utf-8"))
    text = template.read_text(encoding="utf-8")
    missing = sorted({v for v in VAR.findall(text) if not values.get(v)})
    if missing:
        raise SystemExit(f"render: {', '.join(missing)} not set in {env_path}")
    rendered = VAR.sub(lambda m: values[m.group(1)], text)

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not force:
        current = output.read_text(encoding="utf-8")
        if current == rendered:
            return f"{output} is up to date"
        if any(k in current for k in PUBLISHED_DEFAULTS["LITELLM_MASTER_KEY"]):
            # Still on the old published key: it no longer works, so replace (with a backup).
            backup = output.with_name(output.name + ".dev-stack-backup")
            write_private(backup, current)
            write_private(output, rendered)
            return f"replaced {output} (it used the old published key); previous copy: {backup}"
        side = output.with_name(output.name + ".dev-stack-new")
        write_private(side, rendered)
        return f"{output} exists and differs; wrote {side} (compare and merge)"
    write_private(output, rendered)
    return f"wrote {output}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init")
    p_init.add_argument("--env", default=".env")
    p_init.add_argument("--example", default=".env.example")
    p_check = sub.add_parser("check")
    p_check.add_argument("--env", default=".env")
    p_render = sub.add_parser("render")
    p_render.add_argument("template")
    p_render.add_argument("output")
    p_render.add_argument("--env", default=".env")
    p_render.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "init":
        for note in init(Path(args.env), Path(args.example)) or ["nothing to change"]:
            print(f".env: {note}")
        return 0
    if args.cmd == "check":
        problems = check(Path(args.env))
        for p in problems:
            print(f"ERROR: {p}", file=sys.stderr)
        return 1 if problems else 0
    print(render(Path(args.template), Path(os.path.expanduser(args.output)), Path(args.env), args.force))
    return 0


if __name__ == "__main__":
    sys.exit(main())
