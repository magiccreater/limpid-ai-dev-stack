#!/usr/bin/env bash
set -e

mkdir -p "$HOME/tools"
cd "$HOME/tools"

if [ ! -d "llama.cpp" ]; then
  echo "Cloning llama.cpp..."
  git clone https://github.com/ggerganov/llama.cpp
fi

cd llama.cpp
echo "Building llama.cpp with Vulkan acceleration for Intel Arc..."
cmake -B build -DGGML_VULKAN=ON
cmake --build build --config Release -j"$(nproc)"
echo "Build complete: $HOME/tools/llama.cpp/build/bin/llama-server"
