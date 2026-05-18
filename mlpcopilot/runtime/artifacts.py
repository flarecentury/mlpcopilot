"""ArtifactIndex for run manifests and runtime evidence references."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _new_run_id() -> str:
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"run_{stamp}_{uuid.uuid4().hex[:8]}"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


@dataclass(slots=True)
class RunManifest:
    """Runtime-level manifest for one run or tool-produced artifact group."""

    run_id: str = field(default_factory=_new_run_id)
    created_at: str = field(default_factory=_now)
    source: str = ""
    inputs: list[Any] = field(default_factory=list)
    outputs: list[Any] = field(default_factory=list)
    artifacts: list[Any] = field(default_factory=list)
    metrics: list[Any] = field(default_factory=list)
    lineage: dict[str, Any] = field(default_factory=dict)
    decisions: list[Any] = field(default_factory=list)
    approval: Any = None
    errors: list[Any] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "created_at": self.created_at,
            "source": self.source,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "artifacts": self.artifacts,
            "metrics": self.metrics,
            "lineage": self.lineage,
            "decisions": self.decisions,
            "approval": self.approval,
            "errors": self.errors,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunManifest":
        return cls(
            run_id=str(data["run_id"]),
            created_at=str(data.get("created_at") or _now()),
            source=str(data.get("source") or ""),
            inputs=_as_list(data.get("inputs")),
            outputs=_as_list(data.get("outputs")),
            artifacts=_as_list(data.get("artifacts")),
            metrics=_as_list(data.get("metrics")),
            lineage=_as_dict(data.get("lineage")),
            decisions=_as_list(data.get("decisions")),
            approval=data.get("approval"),
            errors=_as_list(data.get("errors")),
            metadata=_as_dict(data.get("metadata")),
        )


class ArtifactIndex:
    """Create, load, and update run manifests under workspace/runs."""

    def __init__(self, workspace: Path):
        self.workspace = workspace.expanduser()
        self.runs_dir = self.workspace / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def create_run(
        self,
        *,
        source: str = "",
        inputs: list[Any] | None = None,
        outputs: list[Any] | None = None,
        artifacts: list[Any] | None = None,
        metrics: list[Any] | None = None,
        lineage: dict[str, Any] | None = None,
        decisions: list[Any] | None = None,
        approval: Any = None,
        errors: list[Any] | None = None,
        metadata: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> RunManifest:
        manifest = RunManifest(
            run_id=run_id or _new_run_id(),
            source=source,
            inputs=inputs or [],
            outputs=outputs or [],
            artifacts=artifacts or [],
            metrics=metrics or [],
            lineage=lineage or {},
            decisions=decisions or [],
            approval=approval,
            errors=errors or [],
            metadata=metadata or {},
        )
        self.save(manifest)
        return manifest

    def save(self, manifest: RunManifest) -> None:
        run_dir = self.runs_dir / manifest.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "manifest.json").write_text(
            json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def load(self, run_id: str) -> RunManifest:
        path = self.runs_dir / run_id / "manifest.json"
        if not path.exists():
            raise FileNotFoundError(f"Run manifest not found: {run_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not data.get("run_id"):
            raise ValueError(f"Invalid run manifest: {path}")
        return RunManifest.from_dict(data)

    def list_runs(self) -> list[RunManifest]:
        manifests: list[RunManifest] = []
        if not self.runs_dir.exists():
            return manifests
        for path in sorted(self.runs_dir.glob("*/manifest.json")):
            try:
                manifests.append(RunManifest.from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, ValueError, json.JSONDecodeError, KeyError):
                continue
        manifests.sort(key=lambda item: item.created_at, reverse=True)
        return manifests

    def update(self, run_id: str, **changes: Any) -> RunManifest:
        manifest = self.load(run_id)
        allowed = {
            "source",
            "inputs",
            "outputs",
            "artifacts",
            "metrics",
            "lineage",
            "decisions",
            "approval",
            "errors",
            "metadata",
        }
        for key, value in changes.items():
            if key in allowed:
                setattr(manifest, key, value)
        self.save(manifest)
        return manifest
