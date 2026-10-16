#!/usr/bin/env bash
# Provision WSL Ubuntu for the dev stack. Safe to re-run.
# Fails loudly: if a step breaks, the script stops and tells you which one.
set -euo pipefail

step() { echo; echo "=== $* ==="; }
trap 'echo; echo "setup.sh FAILED at line $LINENO. Fix the error above and re-run (safe to repeat)." >&2' ERR

# Pinned versions. Bump deliberately, one at a time.
MISE_VERSION="v2026.10.1"
NODE_VERSION="24"          # OpenClaw needs Node >= 24.16
PYTHON_VERSION="3.12"
UV_VERSION="0.12.24"
JUST_VERSION="1.58.0"
LITELLM_VERSION="1.102.2"  # pin exactly: litellm releases on PyPI were compromised in March 2026

step "1. System packages"
sudo apt-get update
sudo apt-get install -y build-essential curl git unzip pkg-config libssl-dev libcurl4-openssl-dev \
  libxml2-dev libsqlite3-dev zlib1g-dev jq software-properties-common \
  ca-certificates ffmpeg libgl1 libglib2.0-0 poppler-utils tesseract-ocr \
  libvulkan-dev vulkan-tools mesa-vulkan-drivers cmake python3-pip

step "2. mise (runtime manager)"
if ! command -v mise >/dev/null && [ ! -x "$HOME/.local/bin/mise" ]; then
  curl -fsSL https://mise.run | MISE_VERSION="$MISE_VERSION" sh
fi
export PATH="$HOME/.local/bin:$PATH"
# shellcheck disable=SC2016  # written literally into .bashrc on purpose
grep -q 'mise activate bash' ~/.bashrc || echo 'eval "$(~/.local/bin/mise activate bash)"' >> ~/.bashrc
eval "$(mise activate bash)"

step "3. Runtimes and tools (node, python, uv, just)"
mise use --global "node@${NODE_VERSION}" "python@${PYTHON_VERSION}" "uv@${UV_VERSION}" "just@${JUST_VERSION}"
eval "$(mise activate bash)"
mise exec -- npm install -g pnpm typescript

step "4. LiteLLM gateway (pinned)"
mise exec -- uv tool install --force "litellm[proxy]==${LITELLM_VERSION}"

step "5. PHP 8.3 + Composer"
if ! command -v php8.3 >/dev/null; then
  sudo add-apt-repository -y ppa:ondrej/php
  sudo apt-get update
  sudo apt-get install -y php8.3-cli php8.3-common php8.3-mbstring php8.3-xml \
    php8.3-curl php8.3-mysql php8.3-zip php8.3-intl php8.3-bcmath
fi
if ! command -v composer >/dev/null; then
  # Official installer with signature check: https://getcomposer.org/download/
  tmp="$(mktemp -d)"
  expected="$(curl -fsSL https://composer.github.io/installer.sig)"
  curl -fsSL https://getcomposer.org/installer -o "$tmp/composer-setup.php"
  actual="$(php -r "echo hash_file('sha384', '$tmp/composer-setup.php');")"
  if [ "$expected" != "$actual" ]; then
    echo "Composer installer signature mismatch; not installing." >&2
    exit 1
  fi
  php "$tmp/composer-setup.php" --quiet --install-dir="$tmp"
  sudo mv "$tmp/composer.phar" /usr/local/bin/composer
  rm -rf "$tmp"
fi

step "6. Docker"
if command -v docker >/dev/null; then
  echo "docker already available ($(docker --version))"
else
  sudo install -m 0755 -d /etc/apt/keyrings
  sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  # shellcheck disable=SC1091
  codename="$(. /etc/os-release && echo "$VERSION_CODENAME")"
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${codename} stable" | \
    sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  sudo usermod -aG docker "$USER"
  echo "Added $USER to the docker group; open a new WSL shell for it to apply."
fi

echo
echo "=== System provisioning complete ==="
echo "Next:"
echo "  source ~/.bashrc"
echo "  just env                    # creates .env with generated secrets"
echo "  # Local model: on Windows run scripts\\windows\\llama-server.ps1 (recommended)"
echo "  #              or in WSL: ./scripts/install_llama.sh && just llama"
echo "  just litellm                # gateway on 127.0.0.1:4000"
echo "  just doctor"
