"""Find and load the dev stack's .env without depending on the current directory."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_loaded = False


def find_env_file() -> Path | None:
    """DEVSTACK_ENV if set, else the nearest .env above this package (the stack root),
    else the nearest .env above the current directory."""
    explicit = os.getenv("DEVSTACK_ENV")
    if explicit:
        return Path(explicit)
    for start in (Path(__file__).resolve().parent, Path.cwd()):
        for folder in (start, *start.parents):
            candidate = folder / ".env"
            if candidate.is_file():
                return candidate
    return None


def load_env() -> Path | None:
    """Load .env once. Variables already set in the environment win."""
    global _loaded
    path = find_env_file()
    if not _loaded and path is not None:
        load_dotenv(path, override=False)
        _loaded = True
    return path
