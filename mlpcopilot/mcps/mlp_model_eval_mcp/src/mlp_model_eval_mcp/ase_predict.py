"""ASE-based DeepMD-kit v3 prediction helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from .deepmd_test import deepmd_v3_model_format
from .schemas import artifact, sha256_file

DEFAULT_STRUCTURE_SUFFIXES = {
    ".cif",
    ".contcar",
    ".extxyz",
    ".pdb",
    ".poscar",
    ".vasp",
    ".xyz",
}


def predict_structure_with_ase(
    *,
    structure_path: Path,
    checkpoint_path: Path,
    structure_format: str | None = None,
    frame_index: int = 0,
    output_path: Path | None = None,
    extxyz_path: Path | None = None,
    head: str | None = None,
    max_inline_atoms: int = 64,
) -> dict[str, Any]:
    """Predict one ASE-readable structure using ``deepmd.calculator.DP``."""
    if not structure_path.is_file():
        return _failed(f"No such structure file: {structure_path}")
    if not checkpoint_path.exists():
        return _failed(f"No such checkpoint path: {checkpoint_path}")
    try:
        atoms = _read_single_atoms(structure_path, structure_format, frame_index)
        prediction = _evaluate_atoms(atoms, checkpoint_path, head=head)
    except Exception as exc:
        return _failed(f"{type(exc).__name__}: {exc}")

    target = output_path or structure_path.with_suffix(structure_path.suffix + ".prediction.json")
    extxyz_target = extxyz_path or structure_path.with_suffix(structure_path.suffix + ".prediction.extxyz")
    target.parent.mkdir(parents=True, exist_ok=True)
    extxyz_target.parent.mkdir(parents=True, exist_ok=True)
    payload = _prediction_payload(
        structure_path=structure_path,
        checkpoint_path=checkpoint_path,
        frame_index=frame_index,
        prediction=prediction,
    )
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    _write_predicted_extxyz(prediction["atoms"], extxyz_target, append=False)
    metrics = _prediction_summary(payload, max_inline_atoms=max_inline_atoms)
    metrics.update(
        {
            "prediction_path": str(target),
            "extxyz_path": str(extxyz_target),
            "model_format": deepmd_v3_model_format(checkpoint_path),
        }
    )
    return {
        "status": "success",
        "summary": f"Predicted energy and forces for {structure_path}.",
        "metrics": metrics,
        "artifacts": [artifact(target, "metrics"), artifact(extxyz_target, "structure")],
        "warnings": [],
        "errors": [],
    }


def batch_predict_with_ase(
    *,
    structure_dir: Path,
    checkpoint_path: Path,
    structure_glob: str = "*",
    recursive: bool = True,
    structure_format: str | None = None,
    output_dir: Path | None = None,
    head: str | None = None,
    max_structures: int = 200,
    write_extxyz: bool = True,
) -> dict[str, Any]:
    """Predict a batch of ASE-readable structure files."""
    if not structure_dir.exists():
        return _failed(f"No such structure path: {structure_dir}")
    if not checkpoint_path.exists():
        return _failed(f"No such checkpoint path: {checkpoint_path}")
    if max_structures <= 0:
        return _failed("max_structures must be positive.")

    run_dir = output_dir or _default_batch_output_dir(structure_dir, checkpoint_path)
    run_dir.mkdir(parents=True, exist_ok=True)
    files = _discover_structure_files(structure_dir, structure_glob, recursive)
    predictions: list[dict[str, Any]] = []
    warnings: list[str] = []
    attempted = 0
    extxyz_path = run_dir / "batch_predictions.extxyz"
    if extxyz_path.exists():
        extxyz_path.unlink()
    for file_path in files:
        if attempted >= max_structures:
            warnings.append(f"Stopped after max_structures={max_structures}.")
            break
        try:
            frames = _read_atoms_frames(file_path, structure_format)
        except Exception as exc:
            warnings.append(f"Skipped {file_path}: {type(exc).__name__}: {exc}")
            continue
        for frame_index, atoms in enumerate(frames):
            if attempted >= max_structures:
                warnings.append(f"Stopped after max_structures={max_structures}.")
                break
            attempted += 1
            try:
                prediction = _evaluate_atoms(atoms, checkpoint_path, head=head)
                payload = _prediction_payload(
                    structure_path=file_path,
                    checkpoint_path=checkpoint_path,
                    frame_index=frame_index,
                    prediction=prediction,
                )
                predictions.append(payload)
                if write_extxyz:
                    _write_predicted_extxyz(
                        prediction["atoms"],
                        extxyz_path,
                        append=extxyz_path.exists(),
                    )
            except Exception as exc:
                warnings.append(f"Failed {file_path} frame {frame_index}: {type(exc).__name__}: {exc}")

    batch_path = run_dir / "batch_predictions.json"
    summary = _batch_summary(
        predictions=predictions,
        checkpoint_path=checkpoint_path,
        structure_path=structure_dir,
        attempted=attempted,
        warnings=warnings,
    )
    batch_payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "summary": summary,
        "predictions": [_drop_atoms(item) for item in predictions],
    }
    batch_path.write_text(json.dumps(batch_payload, indent=2, sort_keys=True), encoding="utf-8")
    artifacts = [artifact(batch_path, "metrics")]
    if write_extxyz and extxyz_path.is_file():
        artifacts.append(artifact(extxyz_path, "structure"))
    status = "success" if predictions else "failed"
    return {
        "status": status,
        "summary": f"Predicted {len(predictions)} structures with ASE/DeepMD."
        if predictions
        else "No structures were predicted.",
        "metrics": {
            **summary,
            "batch_prediction_path": str(batch_path),
            "extxyz_path": str(extxyz_path) if extxyz_path.is_file() else None,
            "model_format": deepmd_v3_model_format(checkpoint_path),
        },
        "artifacts": artifacts,
        "warnings": warnings,
        "errors": [] if predictions else ["No structures were predicted."],
    }


def _read_single_atoms(path: Path, structure_format: str | None, frame_index: int) -> Any:
    frames = _read_atoms_frames(path, structure_format)
    try:
        return frames[frame_index]
    except IndexError as exc:
        raise IndexError(f"frame_index {frame_index} out of range for {path}") from exc


def _read_atoms_frames(path: Path, structure_format: str | None) -> list[Any]:
    from ase.io import read

    kwargs = {"format": structure_format} if structure_format else {}
    try:
        loaded = read(str(path), index=":", **kwargs)
    except TypeError:
        loaded = read(str(path), **kwargs)
    if isinstance(loaded, list):
        return loaded
    return [loaded]


def _evaluate_atoms(atoms: Any, checkpoint_path: Path, *, head: str | None) -> dict[str, Any]:
    from deepmd.calculator import DP

    atoms.calc = DP(model=str(checkpoint_path), head=head)
    energy = float(atoms.get_potential_energy())
    forces = _jsonable_array(atoms.get_forces())
    stress = None
    try:
        stress = _jsonable_array(atoms.get_stress())
    except Exception:
        stress = None
    natoms = len(atoms)
    return {
        "atoms": atoms,
        "formula": atoms.get_chemical_formula(),
        "natoms": natoms,
        "energy": energy,
        "energy_per_atom": energy / natoms if natoms else None,
        "forces": forces,
        "stress": stress,
        "pbc": _jsonable_array(atoms.get_pbc()),
        "cell": _jsonable_array(atoms.get_cell()),
    }


def _prediction_payload(
    *,
    structure_path: Path,
    checkpoint_path: Path,
    frame_index: int,
    prediction: dict[str, Any],
) -> dict[str, Any]:
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "structure_path": str(structure_path),
        "structure_sha256": sha256_file(structure_path),
        "checkpoint_path": str(checkpoint_path),
        "checkpoint_sha256": sha256_file(checkpoint_path) if checkpoint_path.is_file() else None,
        "frame_index": frame_index,
        "formula": prediction["formula"],
        "natoms": prediction["natoms"],
        "energy": prediction["energy"],
        "energy_per_atom": prediction["energy_per_atom"],
        "forces": prediction["forces"],
        "stress": prediction["stress"],
        "pbc": prediction["pbc"],
        "cell": prediction["cell"],
        "inference_executed": True,
    }


def _prediction_summary(payload: dict[str, Any], *, max_inline_atoms: int) -> dict[str, Any]:
    summary = {
        key: payload[key]
        for key in (
            "structure_path",
            "checkpoint_path",
            "frame_index",
            "formula",
            "natoms",
            "energy",
            "energy_per_atom",
            "stress",
            "inference_executed",
        )
    }
    if payload["natoms"] <= max_inline_atoms:
        summary["forces"] = payload["forces"]
    else:
        summary["forces"] = f"omitted; natoms={payload['natoms']} exceeds max_inline_atoms"
    return summary


def _batch_summary(
    *,
    predictions: list[dict[str, Any]],
    checkpoint_path: Path,
    structure_path: Path,
    attempted: int,
    warnings: list[str],
) -> dict[str, Any]:
    energies = [float(item["energy"]) for item in predictions]
    energy_per_atom = [
        float(item["energy_per_atom"])
        for item in predictions
        if item.get("energy_per_atom") is not None
    ]
    return {
        "checkpoint_path": str(checkpoint_path),
        "structure_path": str(structure_path),
        "attempted_count": attempted,
        "prediction_count": len(predictions),
        "warning_count": len(warnings),
        "energy_min": min(energies) if energies else None,
        "energy_max": max(energies) if energies else None,
        "energy_mean": mean(energies) if energies else None,
        "energy_per_atom_mean": mean(energy_per_atom) if energy_per_atom else None,
        "inference_executed": bool(predictions),
    }


def _drop_atoms(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "atoms"}


def _discover_structure_files(root: Path, pattern: str, recursive: bool) -> list[Path]:
    if root.is_file():
        return [root]
    iterator = root.rglob(pattern) if recursive else root.glob(pattern)
    files = [path for path in sorted(iterator) if path.is_file()]
    if pattern == "*":
        files = [path for path in files if path.suffix.lower() in DEFAULT_STRUCTURE_SUFFIXES]
    return files


def _write_predicted_extxyz(atoms: Any, path: Path, *, append: bool) -> None:
    from ase.calculators.singlepoint import SinglePointCalculator
    from ase.io import write

    energy = float(atoms.get_potential_energy())
    forces = atoms.get_forces()
    try:
        stress = atoms.get_stress()
        atoms.calc = SinglePointCalculator(atoms, energy=energy, forces=forces, stress=stress)
    except Exception:
        atoms.calc = SinglePointCalculator(atoms, energy=energy, forces=forces)
    write(str(path), atoms, format="extxyz", append=append)


def _jsonable_array(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, tuple):
        return [_jsonable_array(item) for item in value]
    if isinstance(value, list):
        return [_jsonable_array(item) for item in value]
    return value


def _default_batch_output_dir(structure_dir: Path, checkpoint_path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path.cwd().resolve() / "model_eval_artifacts" / f"{checkpoint_path.stem}-{structure_dir.stem}-{stamp}"


def _failed(message: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "summary": message,
        "metrics": {},
        "artifacts": [],
        "warnings": [],
        "errors": [message],
    }
