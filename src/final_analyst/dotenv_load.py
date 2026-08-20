"""Load project-root .env into process env (no override of existing vars)."""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: Path | None = None, *, override: bool = False) -> Path | None:
    """Parse KEY=VALUE lines from .env. Returns path if loaded."""
    if path is None:
        # final_analyst package -> src -> repo root
        path = Path(__file__).resolve().parents[2] / ".env"
    if not path.exists():
        return None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if not key:
            continue
        if override or key not in os.environ or not os.environ.get(key):
            os.environ[key] = val
    return path
