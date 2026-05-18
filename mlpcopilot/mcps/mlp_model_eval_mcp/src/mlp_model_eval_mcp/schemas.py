"""Shared result helpers for the MLP model evaluation MCP."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

Status = Literal["success", "failed", "blocked"]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact(path: Path, artifact_type: str) -> dict[str, str]:
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
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    if suffix == ".json":
        return json.loads(text)
    if suffix in {".yaml", ".yml"}:
        import yaml

        return yaml.safe_load(text)
    raise ValueError(f"Unsupported metrics/config format: {path}")
