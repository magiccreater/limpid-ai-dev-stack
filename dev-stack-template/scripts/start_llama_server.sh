#!/usr/bin/env bash
set -e

LLAMA_BIN="$HOME/tools/llama.cpp/build/bin/llama-server"
MODEL_DIR="$HOME/models"
MODEL_FILE="$MODEL_DIR/qwen2.5-coder-7b-instruct-q4_k_m.gguf"

if [ ! -f "$LLAMA_BIN" ]; then
  echo "Error: llama-server not found. Run ./scripts/build_llama.sh first."
  exit 1
fi

mkdir -p "$MODEL_DIR"
if [ ! -f "$MODEL_FILE" ]; then
  echo "Downloading Qwen 2.5 Coder 7B (Q4_K_M GGUF) — this is several GB..."
  curl -L -o "$MODEL_FILE" \
    "https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/resolve/main/qwen2.5-coder-7b-instruct-q4_k_m.gguf"
fi

echo "Starting llama-server with Intel Arc offloading (-ngl 99) on :8080..."
exec "$LLAMA_BIN" \
  -m "$MODEL_FILE" \
  --port 8080 \
  --host 0.0.0.0 \
  -ngl 99 \
  -c 4096
