#!/usr/bin/env bash
# Start llama-server inside WSL on 127.0.0.1:8080 (OpenAI-compatible API at /v1).
# For better speed on Intel graphics, run it on Windows instead:
#   powershell -ExecutionPolicy Bypass -File scripts\windows\llama-server.ps1
set -euo pipefail
# shellcheck source=llama_common.sh source-path=SCRIPTDIR
. "$(dirname "$0")/llama_common.sh"

if ! server="$(llama_find_server)"; then
  echo "llama-server not found. Run ./scripts/install_llama.sh first." >&2
  exit 1
fi

if [ -n "${LLAMA_MODEL_FILE:-}" ]; then
  model_args=(-m "$LLAMA_MODEL_FILE")
else
  hf="$(llama_hf_for_preset "$LLAMA_PRESET")"
  model_args=(-hf "$hf")   # downloaded once into ~/.cache/llama.cpp
fi

args=("${model_args[@]}" --host 127.0.0.1 --port 8080 -ngl 99 -c "$LLAMA_CTX" --jinja)
if [ "$LLAMA_N_CPU_MOE" -gt 0 ]; then
  args+=(--n-cpu-moe "$LLAMA_N_CPU_MOE")
fi

echo "Starting: $server ${args[*]}"
exec "$server" "${args[@]}"
