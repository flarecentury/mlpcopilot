"""Shared result helpers for the MLP training controller MCP."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

Status = Literal["success", "failed", "blocked"]


def sha256_file(path: Path) -> str:
    """Return SHA256 for a file without loading it all into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact(path: Path, artifact_type: str) -> dict[str, str]:
    """Return a common artifact record for an existing file."""
    return {
        "type": artifact_type,
        "path": str(path),
        "sha256": sha256_file(path),
    }


def result(
    *,
    status: Status,
    summary: str,
    metrics: dict[str, Any] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> str:
    """Serialize an MCP tool result using the common output protocol."""
    payload = {
        "status": status,
        "summary": summary,
        "metrics": metrics or {},
        "artifacts": artifacts or [],
        "warnings": warnings or [],
        "errors": errors or [],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)


def load_json_or_yaml(path: Path) -> Any:
    """Load JSON or YAML by extension."""
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    if suffix == ".json":
        return json.loads(text)
    if suffix in {".yaml", ".yml"}:
        import yaml

        return yaml.safe_load(text)
    raise ValueError(f"Unsupported file format: {path}")
