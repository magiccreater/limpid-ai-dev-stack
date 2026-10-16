#!/usr/bin/env bash
# Install a prebuilt llama.cpp (Vulkan, Ubuntu x64) release into ~/tools/llama.cpp.
# Faster and more repeatable than building. To build from source: ./scripts/build_llama.sh
set -euo pipefail
# shellcheck source=llama_common.sh source-path=SCRIPTDIR
. "$(dirname "$0")/llama_common.sh"

asset="llama-${LLAMA_CPP_TAG}-bin-ubuntu-vulkan-x64.tar.gz"
url="https://github.com/ggml-org/llama.cpp/releases/download/${LLAMA_CPP_TAG}/${asset}"
dest="$HOME/tools/llama.cpp/${LLAMA_CPP_TAG}"

if [ -x "$HOME/tools/llama.cpp/current/llama-server" ] && \
   [ "$(readlink -f "$HOME/tools/llama.cpp/current")" = "$(readlink -f "$dest" 2>/dev/null || true)" ]; then
  echo "llama.cpp ${LLAMA_CPP_TAG} is already installed."
else
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  echo "Downloading $url"
  curl -fL --retry 3 -o "$tmp/$asset" "$url"
  mkdir -p "$dest"
  tar -xzf "$tmp/$asset" -C "$dest"
  server="$(find "$dest" -type f -name llama-server | head -n 1)"
  if [ -z "$server" ]; then
    echo "ERROR: llama-server not found in $asset" >&2
    exit 1
  fi
  ln -sfn "$(dirname "$server")" "$HOME/tools/llama.cpp/current"
  echo "Installed: $HOME/tools/llama.cpp/current/llama-server"
fi

echo
echo "GPU check (Vulkan devices llama.cpp can see):"
"$HOME/tools/llama.cpp/current/llama-server" --list-devices || true
echo
echo "If no Intel GPU is listed, or only llvmpipe (software), run llama-server on"
echo "Windows instead: scripts/windows/llama-server.ps1 (see README)."
