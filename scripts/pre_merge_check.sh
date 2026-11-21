#!/usr/bin/env bash
set -euo pipefail

# Mandatory local pre-merge check for limpid-ai-dev-stack.
# In the private repository, GitHub Actions skips CI runs (!github.event.repository.private)
# to avoid metered hosted runner minutes.
# This script runs the full verification suite locally in WSL prior to merge or push.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "==> [1/4] ShellCheck..."
if command -v shellcheck >/dev/null 2>&1; then
    shellcheck -x "${REPO_ROOT}/install_dev_stack.sh" \
                  "${REPO_ROOT}/dev-stack-template/setup.sh" \
                  "${REPO_ROOT}"/dev-stack-template/scripts/*.sh
    echo "ShellCheck passed."
else
    echo "Warning: shellcheck not found, skipping."
fi

echo "==> [2/4] CloudFormation lint..."
if command -v uvx >/dev/null 2>&1; then
    uvx cfn-lint==1.57.2 "${REPO_ROOT}/dev-stack-template/aws/bedrock-access.yaml"
    echo "CloudFormation lint passed."
elif command -v cfn-lint >/dev/null 2>&1; then
    cfn-lint "${REPO_ROOT}/dev-stack-template/aws/bedrock-access.yaml"
    echo "CloudFormation lint passed."
else
    echo "Warning: cfn-lint / uvx not found, skipping."
fi

echo "==> [3/4] Installer tests..."
(cd "${REPO_ROOT}" && python3 -m unittest discover -s tests -v)

echo "==> [4/4] Stack tests (shared package, configs, gateway)..."
(cd "${REPO_ROOT}/dev-stack-template" && uv run --project shared --extra test python -m unittest discover -s tests -v)

echo "==> All pre-merge checks passed successfully!"
