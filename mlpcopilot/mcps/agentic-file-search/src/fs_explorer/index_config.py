"""
Configuration helpers for local index storage.
"""

from __future__ import annotations

import os
from pathlib import Path


DEFAULT_DB_PATH = "~/.fs_explorer/index.duckdb"
ENV_DB_PATH = "FS_EXPLORER_DB_PATH"


def resolve_db_path(override_path: str | None = None) -> str:
    """
    Resolve the DuckDB path from CLI override, env var, or default.

    Precedence:
    1) explicit override_path
    2) FS_EXPLORER_DB_PATH
    3) default path
    """
    raw_path = override_path or os.getenv(ENV_DB_PATH) or DEFAULT_DB_PATH
    resolved = Path(raw_path).expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return str(resolved)
