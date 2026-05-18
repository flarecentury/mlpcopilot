"""DP-GEN artifact discovery and normalized artifact rows."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .constants import PRODUCER
from .io import _now, _rel
from .metrics import _artifact_metrics, _log_metrics, _root_log_kind, _stage_metrics
from .record import _iteration_id


def _artifact_id(project_id: str, run_id: str, kind: str, path: Path) -> str:
    raw = f"{project_id}|{run_id}|{kind}|{path}".encode()
    return "art_" + hashlib.sha1(raw).hexdigest()[:16]
def _artifact(
    *,
    workspace: Path,
    project_id: str,
    run_id: str,
    backend_workdir: Path,
    path: Path,
    kind: str,
    role: str,
    name: str | None = None,
    iteration_id: str | None = None,
    status: str = "ready",
    metrics: dict[str, Any] | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "artifact_id": _artifact_id(project_id, run_id, kind, path.resolve()),
        "project_id": project_id,
        "run_id": run_id,
        "iteration_id": iteration_id,
        "kind": kind,
        "role": role,
        "name": name or path.name,
        "path": str(path.resolve()),
        "relative_path": _rel(path, workspace),
        "backend_relative_path": _rel(path, backend_workdir),
        "producer": PRODUCER,
        "source_backend": "dpgen",
        "status": status,
        "created_at": _now(),
        "metrics": metrics or {},
        "tags": tags or ["dpgen"],
        "summary": "",
    }
def _collect_artifacts(workspace: Path, project_id: str, run_id: str, backend_workdir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not backend_workdir.exists():
        return rows

    for pattern in ("param*.json", "machine*.json"):
        for path in sorted(backend_workdir.glob(pattern)):
            if not path.is_file():
                continue
            rows.append(
                _artifact(
                    workspace=workspace,
                    project_id=project_id,
                    run_id=run_id,
                    backend_workdir=backend_workdir,
                    path=path,
                    kind="config",
                    role="input",
                    name=path.name,
                )
            )

    for pattern in ("template*.inp", "template*.pbs", "lmp_*.in"):
        for path in sorted(backend_workdir.glob(pattern)):
            if not path.is_file():
                continue
            rows.append(
                _artifact(
                    workspace=workspace,
                    project_id=project_id,
                    run_id=run_id,
                    backend_workdir=backend_workdir,
                    path=path,
                    kind="template",
                    role="input",
                    name=path.name,
                )
            )

    for pattern in ("graph.*", "frozen_model.*"):
        for path in sorted(backend_workdir.glob(pattern)):
            if not path.is_file():
                continue
            rows.append(
                _artifact(
                    workspace=workspace,
                    project_id=project_id,
                    run_id=run_id,
                    backend_workdir=backend_workdir,
                    path=path,
                    kind="model_checkpoint",
                    role="output",
                    name=path.name,
                )
            )

    for path in sorted(backend_workdir.glob("*.log")):
        if not path.is_file():
            continue
        rows.append(
            _artifact(
                workspace=workspace,
                project_id=project_id,
                run_id=run_id,
                backend_workdir=backend_workdir,
                path=path,
                kind=_root_log_kind(path),
                role="diagnostic",
                name=path.name,
                metrics=_log_metrics(path),
            )
        )

    record_path = backend_workdir / "record.dpgen"
    if record_path.exists():
        rows.append(
            _artifact(
                workspace=workspace,
                project_id=project_id,
                run_id=run_id,
                backend_workdir=backend_workdir,
                path=record_path,
                kind="run_record",
                role="evidence",
                name="record.dpgen",
            )
        )

    iter_dirs = sorted(path for path in backend_workdir.glob("iter.[0-9][0-9][0-9][0-9][0-9][0-9]") if path.is_dir())
    for iter_dir in iter_dirs:
        try:
            iter_index = int(iter_dir.name.split(".")[-1])
        except ValueError:
            continue
        iteration_id = _iteration_id(iter_index)
        train_dir = iter_dir / "00.train"
        model_devi_dir = iter_dir / "01.model_devi"
        fp_dir = iter_dir / "02.fp"
        for stage_dir, kind, role in (
            (train_dir, "training_stage", "evidence"),
            (model_devi_dir, "model_deviation_stage", "evidence"),
            (fp_dir, "fp_stage", "evidence"),
        ):
            if stage_dir.exists():
                rows.append(
                    _artifact(
                        workspace=workspace,
                        project_id=project_id,
                        run_id=run_id,
                        backend_workdir=backend_workdir,
                        path=stage_dir,
                        kind=kind,
                        role=role,
                        name=_rel(stage_dir, backend_workdir),
                        iteration_id=iteration_id,
                        metrics=_stage_metrics(kind, stage_dir),
                    )
                )

        for pattern, kind, role, limit in (
            ("00.train/graph*.pb", "model_checkpoint", "output", 20),
            ("00.train/graph*.pth", "model_checkpoint", "output", 20),
            ("00.train/frozen_model.pb", "model_checkpoint", "output", 20),
            ("00.train/frozen_model.pth", "model_checkpoint", "output", 20),
            ("00.train/*.savedmodel", "model_checkpoint", "output", 20),
            ("00.train/*/graph*.pb", "model_checkpoint", "output", 20),
            ("00.train/*/graph*.pth", "model_checkpoint", "output", 20),
            ("00.train/*/frozen_model.pb", "model_checkpoint", "output", 20),
            ("00.train/*/frozen_model.pth", "model_checkpoint", "output", 20),
            ("00.train/*/*.savedmodel", "model_checkpoint", "output", 20),
            ("00.train/*/checkpoint", "model_checkpoint", "output", 20),
            ("00.train/*/model.ckpt.*", "model_checkpoint", "output", 40),
            ("00.train/*/input.json", "training_input", "input", 20),
            ("00.train/*/lcurve.out", "training_curve", "evidence", 20),
            ("00.train/*/train.log", "training_log", "diagnostic", 20),
            ("01.model_devi/cur_job.json", "job_spec", "input", 20),
            ("01.model_devi/task.*/job.json", "job_spec", "input", 20),
            ("01.model_devi/task.*/model_devi.out", "model_deviation_output", "evidence", 100),
            ("01.model_devi/task.*/model_devi.log", "model_deviation_log", "diagnostic", 20),
            ("02.fp/candidate*.out", "fp_selection_report", "evidence", 50),
            ("02.fp/rest_accurate*.out", "fp_selection_report", "evidence", 50),
            ("02.fp/rest_failed*.out", "fp_selection_report", "evidence", 50),
            ("02.fp/task.*/job.json", "job_spec", "input", 20),
            ("02.fp/task.*/input.inp", "fp_input", "input", 20),
            ("02.fp/task.*/coord.xyz", "fp_input", "input", 20),
            ("02.fp/task.*/output", "fp_output", "evidence", 20),
            ("02.fp/task.*/OUTCAR", "fp_output", "evidence", 20),
            ("02.fp/task.*/vasprun.xml", "fp_output", "evidence", 20),
            ("02.fp/data.*", "label_dataset", "output", 200),
        ):
            matches = sorted(iter_dir.glob(pattern))
            for path in matches[:limit]:
                rows.append(
                    _artifact(
                        workspace=workspace,
                        project_id=project_id,
                        run_id=run_id,
                        backend_workdir=backend_workdir,
                        path=path,
                        kind=kind,
                        role=role,
                        name=_rel(path, backend_workdir),
                        iteration_id=iteration_id,
                        metrics=_artifact_metrics(kind, path),
                    )
                )
    return rows
