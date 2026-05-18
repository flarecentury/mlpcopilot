"""Dataset inspection and lightweight integrity checks."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .schemas import artifact, load_json_or_yaml, result, sha256_file

DEEP_MD_RAW_FILES = {
    "coord.raw",
    "type.raw",
    "box.raw",
    "energy.raw",
    "force.raw",
    "virial.raw",
    "type_map.raw",
}


class DatasetBackend:
    """File-based dataset inspection backend."""

    def inspect_dataset(self, dataset_path: str, max_files: int = 200) -> str:
        path = _resolve(dataset_path)
        if not path.exists():
            return result(
                status="failed",
                summary="Dataset path does not exist.",
                metrics={"dataset_path": str(path)},
                errors=[f"No such path: {path}"],
            )
        try:
            inventory = inspect_dataset_path(path, max_files=max_files)
        except OSError as exc:
            return result(
                status="failed",
                summary="Failed to inspect dataset.",
                metrics={"dataset_path": str(path)},
                errors=[f"{type(exc).__name__}: {exc}"],
            )
        return result(
            status="success",
            summary=f"Inspected dataset path: {path}",
            metrics=inventory,
            warnings=inventory.get("warnings") if isinstance(inventory.get("warnings"), list) else [],
        )

    def validate_dataset_schema(self, dataset_path: str, schema_path: str) -> str:
        dataset = _resolve(dataset_path)
        schema_file = _resolve(schema_path)
        errors: list[str] = []
        warnings: list[str] = []
        if not dataset.exists():
            errors.append(f"No such dataset path: {dataset}")
        if not schema_file.is_file():
            errors.append(f"No such schema file: {schema_file}")
        schema: dict[str, Any] = {}
        if not errors:
            try:
                loaded = load_json_or_yaml(schema_file)
                if not isinstance(loaded, dict):
                    errors.append("Schema must be a JSON/YAML object.")
                else:
                    schema = loaded
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
        required = schema.get("required_files") if isinstance(schema, dict) else None
        missing: list[str] = []
        if isinstance(required, list):
            for raw in required:
                if not isinstance(raw, str):
                    warnings.append(f"Ignored non-string required_files entry: {raw!r}")
                    continue
                if not (dataset / raw).exists():
                    missing.append(raw)
        elif schema:
            warnings.append("Schema has no required_files list; only basic schema readability was checked.")
        if missing:
            errors.extend(f"Missing required file: {item}" for item in missing)
        return result(
            status="failed" if errors else "success",
            summary="Dataset schema validation failed." if errors else "Dataset schema validation passed.",
            metrics={
                "dataset_path": str(dataset),
                "schema_path": str(schema_file),
                "required_files": required if isinstance(required, list) else [],
                "missing_files": missing,
            },
            artifacts=[artifact(schema_file, "config")] if schema_file.is_file() else [],
            warnings=warnings,
            errors=errors,
        )

    def validate_dataset_integrity(self, dataset_path: str, max_files: int = 500) -> str:
        path = _resolve(dataset_path)
        if not path.exists():
            return result(
                status="failed",
                summary="Dataset path does not exist.",
                metrics={"dataset_path": str(path)},
                errors=[f"No such path: {path}"],
            )
        errors: list[str] = []
        warnings: list[str] = []
        checks: list[dict[str, Any]] = []
        try:
            if path.is_file():
                checks.extend(_validate_dataset_file(path))
            else:
                systems = find_deepmd_raw_systems(path, max_files=max_files)
                if systems:
                    checks.extend(_validate_deepmd_raw_system(system) for system in systems)
                else:
                    warnings.append("No recognized DeepMD raw system was found; performed file readability inventory only.")
                checks.append(_validate_readability(path, max_files=max_files))
        except OSError as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
        for check in checks:
            errors.extend(str(item) for item in check.get("errors", []) if item)
            warnings.extend(str(item) for item in check.get("warnings", []) if item)
        return result(
            status="failed" if errors else "success",
            summary="Lightweight dataset integrity validation failed."
            if errors
            else "Lightweight dataset integrity validation passed.",
            metrics={
                "dataset_path": str(path),
                "scope": "file_layout_and_basic_integrity_only",
                "not_checked": _not_checked_scientific_checks(),
                "checks": checks,
                "check_count": len(checks),
            },
            warnings=warnings,
            errors=errors,
        )

    def build_dataset_validation_report(
        self,
        dataset_path: str,
        output_path: str | None = None,
        max_files: int = 500,
    ) -> str:
        path = _resolve(dataset_path)
        report_path = _resolve(output_path) if output_path else _default_report_path(path)
        inspect_payload = json.loads(self.inspect_dataset(str(path), max_files=max_files))
        integrity_payload = json.loads(self.validate_dataset_integrity(str(path), max_files=max_files))
        errors: list[str] = []
        artifacts_payload: list[dict[str, Any]] = []
        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                _validation_report_markdown(path, inspect_payload, integrity_payload),
                encoding="utf-8",
            )
            artifacts_payload.append(artifact(report_path, "report"))
        except OSError as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
        status = "failed" if errors or integrity_payload.get("status") == "failed" else "success"
        return result(
            status=status,
            summary=f"Wrote lightweight dataset validation report: {report_path}"
            if not errors
            else "Failed to write dataset validation report.",
            metrics={
                "dataset_path": str(path),
                "report_path": str(report_path),
                "inspect_status": inspect_payload.get("status"),
                "integrity_status": integrity_payload.get("status"),
                "scope": "file_layout_and_basic_integrity_only",
                "not_checked": _not_checked_scientific_checks(),
            },
            artifacts=artifacts_payload,
            warnings=[
                *(inspect_payload.get("warnings") or []),
                *(integrity_payload.get("warnings") or []),
            ],
            errors=[
                *(integrity_payload.get("errors") or []),
                *errors,
            ],
        )


def inspect_dataset_path(path: Path, *, max_files: int = 200) -> dict[str, Any]:
    if path.is_file():
        return {
            "dataset_path": str(path),
            "kind": "file",
            "format": _dataset_file_format(path),
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
            "frames": _count_extxyz_frames(path) if path.suffix.lower() in {".xyz", ".extxyz"} else None,
            "warnings": [],
        }
    files = [item for item in sorted(path.rglob("*")) if item.is_file()]
    sampled = files[:max_files]
    systems = find_deepmd_raw_systems(path, max_files=max_files)
    return {
        "dataset_path": str(path),
        "kind": "directory",
        "format": "deepmd_raw" if systems else "directory",
        "file_count": len(files),
        "sampled_file_count": len(sampled),
        "total_size_bytes": sum(item.stat().st_size for item in sampled),
        "deepmd_raw_systems": [_deepmd_system_summary(system) for system in systems],
        "sample_files": [
            {
                "path": str(item),
                "size_bytes": item.stat().st_size,
                "sha256": sha256_file(item),
            }
            for item in sampled
        ],
        "warnings": ["File inventory truncated by max_files."] if len(files) > max_files else [],
    }


def find_deepmd_raw_systems(root: Path, *, max_files: int = 500) -> list[Path]:
    systems: list[Path] = []
    for directory in [root, *(path for path in root.rglob("*") if path.is_dir())]:
        names = {item.name for item in directory.iterdir() if item.is_file()}
        if {"coord.raw", "type.raw"}.issubset(names):
            systems.append(directory)
        if len(systems) >= max_files:
            break
    return systems


def _validate_deepmd_raw_system(system: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    files = {item.name: item for item in system.iterdir() if item.is_file()}
    natoms = _count_type_raw(files.get("type.raw"))
    frame_counts: dict[str, int] = {}
    for name in ("coord.raw", "box.raw", "energy.raw", "force.raw", "virial.raw"):
        path = files.get(name)
        if path is not None:
            frame_counts[name] = _nonempty_line_count(path)
    if natoms <= 0:
        errors.append(f"{system}: type.raw is missing or empty.")
    if "coord.raw" not in frame_counts:
        errors.append(f"{system}: coord.raw is required for DeepMD raw data.")
    expected_frames = frame_counts.get("coord.raw")
    for name, count in frame_counts.items():
        if expected_frames is not None and count != expected_frames:
            errors.append(f"{system}: {name} has {count} frames, expected {expected_frames}.")
    for name, width in (("coord.raw", 3 * natoms), ("force.raw", 3 * natoms), ("box.raw", 9), ("virial.raw", 9)):
        path = files.get(name)
        if path is not None and natoms > 0:
            mismatch = _first_width_mismatch(path, width)
            if mismatch is not None:
                errors.append(f"{path}: line {mismatch[0]} has {mismatch[1]} values, expected {width}.")
    missing_optional = sorted(DEEP_MD_RAW_FILES - set(files))
    if "energy.raw" not in files and "force.raw" not in files:
        warnings.append(f"{system}: neither energy.raw nor force.raw was found.")
    return {
        "kind": "deepmd_raw_system",
        "path": str(system),
        "natoms": natoms,
        "frames": expected_frames,
        "frame_counts": frame_counts,
        "files": sorted(set(files) & DEEP_MD_RAW_FILES),
        "missing_optional_files": missing_optional,
        "errors": errors,
        "warnings": warnings,
    }


def _validate_dataset_file(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() in {".xyz", ".extxyz"}:
        parsed = _count_extxyz_frames(path)
        errors = parsed.get("errors", [])
        return [
            {
                "kind": "extxyz",
                "path": str(path),
                "frames": parsed.get("frames"),
                "atoms": parsed.get("atoms"),
                "errors": errors,
                "warnings": [],
            }
        ]
    return [
        {
            "kind": "file_readability",
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "errors": [],
            "warnings": ["No format-specific integrity checker is available for this file suffix."],
        }
    ]


def _validate_readability(path: Path, *, max_files: int) -> dict[str, Any]:
    errors: list[str] = []
    files = [item for item in sorted(path.rglob("*")) if item.is_file()][:max_files]
    for item in files:
        try:
            item.open("rb").close()
        except OSError as exc:
            errors.append(f"{item}: {type(exc).__name__}: {exc}")
    return {
        "kind": "file_readability",
        "path": str(path),
        "sampled_file_count": len(files),
        "errors": errors,
        "warnings": [],
    }


def _deepmd_system_summary(system: Path) -> dict[str, Any]:
    files = {item.name: item for item in system.iterdir() if item.is_file()}
    natoms = _count_type_raw(files.get("type.raw"))
    frames = _nonempty_line_count(files["coord.raw"]) if "coord.raw" in files else None
    return {
        "path": str(system),
        "natoms": natoms,
        "frames": frames,
        "files": sorted(set(files) & DEEP_MD_RAW_FILES),
    }


def _count_type_raw(path: Path | None) -> int:
    if path is None or not path.is_file():
        return 0
    text = path.read_text(encoding="utf-8", errors="replace")
    return len([item for item in text.split() if item.strip()])


def _nonempty_line_count(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip())


def _first_width_mismatch(path: Path, width: int) -> tuple[int, int] | None:
    for index, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        if not line.strip():
            continue
        count = len(line.split())
        if count != width:
            return index, count
    return None


def _count_extxyz_frames(path: Path) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    index = 0
    frames = 0
    atoms = 0
    errors: list[str] = []
    while index < len(lines):
        raw = lines[index].strip()
        if not raw:
            index += 1
            continue
        try:
            natoms = int(raw)
        except ValueError:
            errors.append(f"Line {index + 1}: expected atom count, got {raw!r}.")
            break
        if natoms < 0:
            errors.append(f"Line {index + 1}: atom count must be non-negative.")
            break
        end = index + 2 + natoms
        if end > len(lines):
            errors.append(f"Frame {frames + 1}: expected {natoms} atom lines, file ended early.")
            break
        frames += 1
        atoms += natoms
        index = end
    return {"frames": frames, "atoms": atoms, "errors": errors}


def _dataset_file_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".extxyz":
        return "extxyz"
    if suffix == ".xyz":
        return "xyz"
    if suffix in {".npy", ".npz"}:
        return "numpy"
    if suffix in {".json", ".yaml", ".yml"}:
        return "metadata"
    return suffix.lstrip(".") or "file"


def _validation_report_markdown(path: Path, inspect_payload: dict[str, Any], integrity_payload: dict[str, Any]) -> str:
    metrics = inspect_payload.get("metrics") if isinstance(inspect_payload.get("metrics"), dict) else {}
    integrity = integrity_payload.get("metrics") if isinstance(integrity_payload.get("metrics"), dict) else {}
    lines = [
        "# Dataset Validation Report",
        "",
        f"- Dataset: `{path}`",
        f"- Created: `{datetime.now(tz=UTC).isoformat()}`",
        f"- Inspect status: `{inspect_payload.get('status')}`",
        f"- Integrity status: `{integrity_payload.get('status')}`",
        f"- Format: `{metrics.get('format')}`",
        f"- File count: `{metrics.get('file_count', 1 if path.is_file() else 0)}`",
        "",
        "## Scope and Limitations",
        "",
        "This report is a lightweight file-layout and basic integrity check. It can record inventory, hashes, "
        "simple schema/file-presence checks, DeepMD raw frame-count consistency, extxyz framing, and file readability.",
        "",
        "It does not check unit consistency, structure sanity, duplicate or near-duplicate structures, train/test split leakage, "
        "label consistency, label outliers, local-environment coverage, OOD coverage, or checkpoint/deployment readiness.",
        "",
        "## Checks",
        "",
    ]
    for check in integrity.get("checks") or []:
        if not isinstance(check, dict):
            continue
        lines.append(f"- `{check.get('kind')}` `{check.get('path')}`")
        for err in check.get("errors") or []:
            lines.append(f"  - error: {err}")
        for warning in check.get("warnings") or []:
            lines.append(f"  - warning: {warning}")
    if integrity_payload.get("errors"):
        lines.extend(["", "## Errors", ""])
        for err in integrity_payload["errors"]:
            lines.append(f"- {err}")
    if integrity_payload.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        for warning in integrity_payload["warnings"]:
            lines.append(f"- {warning}")
    return "\n".join(lines).rstrip() + "\n"


def _not_checked_scientific_checks() -> list[str]:
    return [
        "unit_consistency",
        "structure_sanity",
        "duplicate_or_near_duplicate_structures",
        "train_test_split_leakage",
        "label_consistency",
        "label_outliers",
        "local_environment_coverage",
        "ood_coverage",
        "checkpoint_or_deployment_readiness",
    ]


def _default_report_path(path: Path) -> Path:
    base = path if path.is_dir() else path.parent
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    return base / "reports" / f"dataset_validation_{stamp}.md"


def _resolve(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)
