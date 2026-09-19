#!/usr/bin/env bash
set -e

echo "=== 1. System packages ==="
sudo apt update
sudo apt install -y build-essential curl git unzip pkg-config libssl-dev \
  libxml2-dev libsqlite3-dev zlib1g-dev jq software-properties-common \
  ca-certificates apt-transport-https ffmpeg libgl1 libglib2.0-0 \
  poppler-utils tesseract-ocr libvulkan-dev vulkan-tools cmake \
  python3-pip

echo "=== 2. mise + uv ==="
if [ ! -f "$HOME/.local/bin/mise" ]; then
  curl https://mise.run | sh
fi
grep -q 'mise activate bash' ~/.bashrc || echo 'eval "$(~/.local/bin/mise activate bash)"' >> ~/.bashrc
eval "$(~/.local/bin/mise activate bash)"

if [ ! -f "$HOME/.local/bin/uv" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

echo "=== 3. Runtimes ==="
mise use --global node@lts
npm install -g pnpm typescript ts-node 2>/dev/null || true
mise use --global python@3.11

# PHP (LAMP)
sudo add-apt-repository -y ppa:ondrej/php 2>/dev/null || true
sudo apt update
sudo apt install -y php8.3-cli php8.3-common php8.3-mbstring php8.3-xml \
  php8.3-curl php8.3-mysql php8.3-zip php8.3-intl php8.3-bcmath || true

if [ ! -f /usr/local/bin/composer ]; then
  curl -sS https://getcomposer.org/installer | php
  sudo mv composer.phar /usr/local/bin/composer
fi

echo "=== 4. Docker ==="
if ! command -v docker &>/dev/null; then
  sudo install -m 0755 -d /etc/apt/keyrings
  sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
    sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  sudo apt update
  sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  sudo usermod -aG docker "$USER"
fi

echo "=== 5. just ==="
if ! command -v just &>/dev/null; then
  curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to "$HOME/.local/bin"
fi

echo "=== 6. Python agent deps (shared) ==="
uv pip install --system httpx python-dotenv langchain-openai yfinance playwright 2>/dev/null || \
  pip install httpx python-dotenv langchain-openai yfinance playwright || true

echo "=== System provisioning complete ==="
echo "Next:"
echo "  source ~/.bashrc"
echo "  just env"
echo "  ./scripts/build_llama.sh"
echo "  ./scripts/setup_openclaw.sh"
echo "  just llama &  just litellm &  just mysql"
