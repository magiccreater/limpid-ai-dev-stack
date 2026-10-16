#!/usr/bin/env bash
# Build llama.cpp from source with Vulkan, pinned to LLAMA_CPP_TAG.
# Most people should use ./scripts/install_llama.sh (prebuilt) instead.
set -euo pipefail
# shellcheck source=llama_common.sh source-path=SCRIPTDIR
. "$(dirname "$0")/llama_common.sh"

src="$HOME/tools/llama.cpp-src"
if [ ! -d "$src/.git" ]; then
  git clone https://github.com/ggml-org/llama.cpp "$src"
fi
git -C "$src" fetch --tags --quiet origin
git -C "$src" checkout --quiet "$LLAMA_CPP_TAG"

echo "Building llama.cpp $LLAMA_CPP_TAG with Vulkan..."
cmake -S "$src" -B "$src/build" -DGGML_VULKAN=ON -DCMAKE_BUILD_TYPE=Release
cmake --build "$src/build" --config Release -j"$(nproc)" --target llama-server
echo "Built: $src/build/bin/llama-server"
"$src/build/bin/llama-server" --list-devices || true
