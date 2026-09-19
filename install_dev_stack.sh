#!/usr/bin/env bash
# Install the full productive local development stack into ~/dev-stack
set -e

REPO_DIR="$HOME/dev-stack"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="$SCRIPT_DIR/dev-stack-template"

echo "=== Installing Dev Stack to $REPO_DIR ==="

if [ -d "$REPO_DIR" ] && [ "$(ls -A "$REPO_DIR" 2>/dev/null)" ]; then
  echo "WARNING: $REPO_DIR already exists and is not empty."
  read -r -p "Overwrite? [y/N] " ans
  if [[ ! "$ans" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
  fi
  rm -rf "$REPO_DIR"
fi

mkdir -p "$REPO_DIR"
cp -a "$TEMPLATE/." "$REPO_DIR/"
chmod +x "$REPO_DIR/setup.sh" "$REPO_DIR/scripts/"*.sh 2>/dev/null || true

cd "$REPO_DIR"

# Minimal git init
if [ ! -d .git ]; then
  git init -b main
  git add .
  git commit -m "Initial commit: productive local multi-agent dev stack" || true
fi

echo ""
echo "=== Done ==="
echo "cd ~/dev-stack"
echo "./setup.sh"
echo "source ~/.bashrc"
echo "just env          # creates .env from example"
echo "# edit .env → set OPENROUTER_API_KEY"
echo "./scripts/build_llama.sh"
echo "./scripts/setup_openclaw.sh"
echo "just llama & just litellm & just mysql"
echo ""
echo "Agents: just agent coding|scraper|social|trend|stock|mentor|study"
echo "Open VS Code on this folder (Remote-WSL) and install recommended extensions."
