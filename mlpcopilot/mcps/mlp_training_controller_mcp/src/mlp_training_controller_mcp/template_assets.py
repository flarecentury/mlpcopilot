"""Template and asset discovery for training backend configuration files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schemas import artifact


@dataclass(slots=True)
class TemplateCheck:
    """A discovered template or asset reference."""

    role: str
    raw_path: str
    resolved_path: Path
    exists: bool
    variables: list[str]
    missing_variables: list[str]

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "role": self.role,
            "path": str(self.resolved_path),
            "raw_path": self.raw_path,
            "exists": self.exists,
            "variables": self.variables,
            "missing_variables": self.missing_variables,
        }
        if self.exists and self.resolved_path.is_file():
            payload["artifact"] = artifact(self.resolved_path, "config")
        return payload


def resolve_asset(base_dir: Path, raw_path: Any) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    return candidate.resolve(strict=False)


def _template_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _placeholder_present(text: str, variable: str) -> bool:
    patterns = (
        rf"\b{re.escape(variable)}\b",
        rf"\$\{{{re.escape(variable)}\}}",
        rf"\bV_{re.escape(variable)}\b",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def _rev_mat_variables(rev_mat: Any) -> list[str]:
    if not isinstance(rev_mat, dict):
        return []
    variables: set[str] = set()
    for engine_payload in rev_mat.values():
        if isinstance(engine_payload, dict):
            variables.update(str(key) for key in engine_payload)
    return sorted(variables)


def _cp2k_referenced_assets(template_path: Path, text: str) -> list[tuple[str, str]]:
    """Return simple CP2K file references declared inside an input template."""
    refs: list[tuple[str, str]] = []
    patterns = {
        "basis_set_file": re.compile(r"^\s*BASIS_SET_FILE_NAME\s+(.+?)\s*$", re.I | re.M),
        "potential_file": re.compile(r"^\s*POTENTIAL_FILE_NAME\s+(.+?)\s*$", re.I | re.M),
        "parameter_file": re.compile(r"^\s*PARAMETER_FILE_NAME\s+(.+?)\s*$", re.I | re.M),
        "include": re.compile(r"^\s*@include\s+(.+?)\s*$", re.I | re.M),
    }
    for role, pattern in patterns.items():
        for match in pattern.finditer(text):
            raw = match.group(1).strip().strip('"').strip("'")
            if not raw or "$" in raw or raw.lower() in {"none", "leave"}:
                continue
            refs.append((f"dpgen.fp.cp2k.{role}", raw))
    return refs


def collect_dpgen_template_checks(
    *,
    project_path: Path,
    param_path: Path,
    param_data: dict[str, Any],
) -> list[TemplateCheck]:
    """Collect DP-GEN template and backend asset checks."""
    base_dir = param_path.parent if param_path.parent.exists() else project_path
    checks: list[TemplateCheck] = []

    for idx, job in enumerate(param_data.get("model_devi_jobs") or []):
        if not isinstance(job, dict):
            continue
        template = job.get("template")
        if isinstance(template, dict):
            for engine, raw_path in template.items():
                resolved = resolve_asset(base_dir, raw_path)
                if resolved is None:
                    continue
                text = _template_text(resolved) if resolved.exists() else ""
                variables = _rev_mat_variables(job.get("rev_mat"))
                missing = [name for name in variables if not _placeholder_present(text, name)]
                checks.append(
                    TemplateCheck(
                        role=f"dpgen.model_devi.{engine}.job_{idx}",
                        raw_path=str(raw_path),
                        resolved_path=resolved,
                        exists=resolved.is_file(),
                        variables=variables,
                        missing_variables=missing,
                    )
                )

    asset_keys = (
        ("dpgen.fp.external_input", "external_input_path"),
        ("dpgen.fp.incar", "fp_incar"),
        ("dpgen.fp.kpt", "fp_kpt"),
        ("dpgen.fp.pp_path", "fp_pp_path"),
    )
    for role, key in asset_keys:
        raw_path = param_data.get(key)
        resolved = resolve_asset(base_dir, raw_path)
        if resolved is not None:
            checks.append(
                TemplateCheck(
                    role=role,
                    raw_path=str(raw_path),
                    resolved_path=resolved,
                    exists=resolved.exists(),
                    variables=[],
                    missing_variables=[],
                )
            )
            if key == "external_input_path" and resolved.is_file():
                text = _template_text(resolved)
                for child_role, child_raw in _cp2k_referenced_assets(resolved, text):
                    child = resolve_asset(resolved.parent, child_raw)
                    if child is None:
                        continue
                    checks.append(
                        TemplateCheck(
                            role=child_role,
                            raw_path=child_raw,
                            resolved_path=child,
                            exists=child.exists(),
                            variables=[],
                            missing_variables=[],
                        )
                    )

    return checks
