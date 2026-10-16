# shellcheck shell=bash
# Shared settings for the llama.cpp scripts. Source it; do not run it.
# Values come from the environment first, then from .env, then the defaults below.

LLAMA_CPP_TAG_DEFAULT="b11600"   # pinned llama.cpp release; bump deliberately

_stack_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -f "$_stack_root/.env" ]; then
  while IFS='=' read -r _k _v; do
    case "$_k" in
      LLAMA_PRESET|LLAMA_CTX|LLAMA_N_CPU_MOE|LLAMA_CPP_TAG|LLAMA_MODEL_FILE)
        _v="${_v%\"}"; _v="${_v#\"}"
        if [ -z "${!_k:-}" ]; then export "$_k=$_v"; fi ;;
    esac
  done < <(grep -E '^LLAMA_[A-Z_]+=' "$_stack_root/.env" || true)
fi

LLAMA_CPP_TAG="${LLAMA_CPP_TAG:-$LLAMA_CPP_TAG_DEFAULT}"
LLAMA_PRESET="${LLAMA_PRESET:-qwen36}"
LLAMA_CTX="${LLAMA_CTX:-32768}"
LLAMA_N_CPU_MOE="${LLAMA_N_CPU_MOE:-0}"

llama_hf_for_preset() {
  case "$1" in
    qwen36) echo "ggml-org/Qwen3.6-35B-A3B-GGUF:Q4_K_M" ;;      # about 20 GB
    small)  echo "Qwen/Qwen2.5-Coder-7B-Instruct-GGUF:Q4_K_M" ;; # about 5 GB
    *) echo "Unknown LLAMA_PRESET '$1' (use qwen36 or small, or set LLAMA_MODEL_FILE)" >&2; return 1 ;;
  esac
}

# First llama-server found: $LLAMA_BIN, prebuilt install, source build, PATH.
llama_find_server() {
  local c
  for c in "${LLAMA_BIN:-}" \
           "$HOME/tools/llama.cpp/current/llama-server" \
           "$HOME/tools/llama.cpp-src/build/bin/llama-server" \
           "$(command -v llama-server 2>/dev/null || true)"; do
    if [ -n "$c" ] && [ -x "$c" ]; then echo "$c"; return 0; fi
  done
  return 1
}
