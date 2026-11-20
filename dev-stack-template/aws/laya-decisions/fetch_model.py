"""Bake only the approved public Laya checkpoint and tokenizer into the image."""

from pathlib import Path

CHECKPOINT = "fd4f9dbcf4fde222fd43174bdd4c3b08b789e4e1"
ROOT = Path("/opt/laya-model")

if __name__ == "__main__":
    from huggingface_hub import snapshot_download

    snapshot_download(
        repo_id="convaiinnovations/laya",
        revision=CHECKPOINT,
        local_dir=ROOT,
        allow_patterns=["typed-decisions/encoder/config.json", "typed-decisions/model.safetensors",
                        "typed-decisions/rl_agent_config.json", "typed-decisions/tokenizer/*.json"],
    )
