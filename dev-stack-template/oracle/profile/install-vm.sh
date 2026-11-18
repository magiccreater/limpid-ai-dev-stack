#!/usr/bin/env bash
set -euo pipefail
cd /opt/god-inference
export DEBIAN_FRONTEND=noninteractive
apt-get -qq update
apt-get -o DPkg::Lock::Timeout=300 -qq install -y cmake build-essential git curl ca-certificates python3 libssl-dev
rev=10f173b253173e9cca4e81a4803a0f01989d1b29
if [[ ! -x bin/llama-server || "$(cat build-revision 2>/dev/null || true)" != "$rev" ]]; then
  git init -q llama
  git -C llama fetch -q --depth=1 https://github.com/ggml-org/llama.cpp "$rev"
  git -C llama checkout -q --detach FETCH_HEAD
  cmake -S llama -B build -DBUILD_SHARED_LIBS=OFF -DGGML_NATIVE=ON -DLLAMA_BUILD_TESTS=OFF -DCMAKE_BUILD_TYPE=Release
  cmake --build build --target llama-server --parallel 2
  install -D build/bin/llama-server bin/llama-server
  echo "$rev" > build-revision
fi
if [[ ! -s coder.gguf ]]; then
  curl --fail --location --retry 3 --continue-at - -o coder.part 'https://huggingface.co/bartowski/Qwen2.5-Coder-3B-Instruct-GGUF/resolve/7c137640ef0332dfedb229f2504c58d83ed4307a/Qwen2.5-Coder-3B-Instruct-Q4_K_M.gguf'
  echo '3da3afe6cf5c674ac195803ea0dd6fee7e1c228c2105c1ce8c66890d1d4ab460  coder.part' | sha256sum --check || {
    mv coder.part "coder.invalid.$(date +%s)"; exit 1; }
  mv coder.part coder.gguf
fi
for name in inference router; do
  if [[ "$name" == inference ]]; then
    command='/opt/god-inference/bin/llama-server -m /opt/god-inference/coder.gguf --alias oci-local --host 127.0.0.1 --port 8181 -c 24576 -t 2 -np 1 --jinja'
  else
    command='/usr/bin/python3 /opt/god-inference/gateway.py'
  fi
  cat > "/etc/systemd/system/god-$name.service" <<EOF
[Unit]
Description=God kit $name
After=network.target
[Service]
ExecStart=$command
DynamicUser=yes
StateDirectory=god-$name
Environment=USAGE_DB=/var/lib/god-$name/usage.sqlite
EnvironmentFile=-/etc/god-$name.env
NoNewPrivileges=yes
ProtectHome=yes
ProtectSystem=strict
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF
done
systemctl daemon-reload
systemctl enable god-inference god-router
systemctl restart god-inference god-router
