#!/usr/bin/env bash
# Install OpenClaw (pinned npm release) and write its config pointing at LiteLLM.
set -euo pipefail

OPENCLAW_VERSION="${OPENCLAW_VERSION:-2026.10.4}"   # bump deliberately
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Installing OpenClaw $OPENCLAW_VERSION ==="
if ! command -v npm >/dev/null; then
  echo "npm not found. Run ./setup.sh first (installs Node 24 with mise)." >&2
  exit 1
fi
npm install -g "openclaw@${OPENCLAW_VERSION}"

echo "=== Writing config ==="
python3 "$ROOT/scripts/devstack_env.py" check --env "$ROOT/.env"
python3 "$ROOT/scripts/devstack_env.py" render --env "$ROOT/.env" \
  "$ROOT/clients/openclaw.json.tmpl" "$HOME/.openclaw/openclaw.json"

echo ""
echo "Next steps:"
echo "  1. Ensure LiteLLM is running: just litellm"
echo "  2. openclaw onboard   # or openclaw models list"
echo "  3. openclaw gateway"
echo "  4. openclaw dashboard"
echo ""
echo "WhatsApp: openclaw channels login whatsapp. Keep dmPolicy on pairing/allowlist."
