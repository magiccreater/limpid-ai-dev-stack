#!/usr/bin/env bash
set -e

echo "=== Installing OpenClaw ==="
if ! command -v openclaw &>/dev/null; then
  curl -fsSL https://openclaw.ai/install.sh | bash
fi

echo "=== Writing example config ==="
mkdir -p ~/.openclaw
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ ! -f ~/.openclaw/openclaw.json ]; then
  cp "$REPO_ROOT/openclaw/openclaw.json.example" ~/.openclaw/openclaw.json
  echo "Created ~/.openclaw/openclaw.json"
else
  echo "Config already exists — not overwriting"
fi

echo ""
echo "Next steps:"
echo "  1. Ensure LiteLLM is running: just litellm"
echo "  2. openclaw onboard   # or openclaw models list"
echo "  3. openclaw gateway"
echo "  4. openclaw dashboard"
echo ""
echo "WhatsApp: openclaw channels login whatsapp (or use Control UI)"
