"""Config generation helpers for training controller backends."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .schemas import artifact, load_json_or_yaml
from .secret_redactor import redact_mapping


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _deep_update(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
    return base


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _repeat_auto(count: int) -> list[str]:
    return ["auto" for _ in range(max(count, 0))]


def _default_training_param(elements: list[str], strategy: dict[str, Any]) -> dict[str, Any]:
    descriptor_sel = strategy.get("descriptor_sel") or [128 for _ in elements]
    return {
        "model": {
            "type_map": elements,
            "descriptor": {
                "type": strategy.get("descriptor_type", "se_e2_a"),
                "sel": descriptor_sel,
                "rcut_smth": strategy.get("rcut_smth", 0.5),
                "rcut": strategy.get("rcut", 8.0),
                "neuron": strategy.get("descriptor_neuron", [20, 40, 80]),
                "resnet_dt": False,
                "axis_neuron": strategy.get("axis_neuron", 12),
                "seed": 1,
                "precision": "default",
            },
            "fitting_net": {
                "type": "ener",
                "neuron": strategy.get("fitting_neuron", [200, 200, 200]),
                "resnet_dt": False,
                "seed": 1,
                "numb_fparam": 0,
                "numb_aparam": 0,
                "precision": "default",
                "trainable": True,
                "rcond": None,
                "atom_ener": [],
                "use_aparam_as_mask": False,
            },
        },
        "learning_rate": {
            "type": "exp",
            "start_lr": strategy.get("start_lr", 0.001),
            "decay_steps": strategy.get("decay_steps", 1000),
            "scale_by_worker": strategy.get("scale_by_worker", "linear"),
            "stop_lr": strategy.get("stop_lr", 1e-8),
        },
        "loss": {
            "start_pref_e": strategy.get("start_pref_e", 0.02),
            "limit_pref_e": strategy.get("limit_pref_e", 1),
            "start_pref_f": strategy.get("start_pref_f", 1000),
            "limit_pref_f": strategy.get("limit_pref_f", 1),
            "start_pref_v": strategy.get("start_pref_v", 0.02),
            "limit_pref_v": strategy.get("limit_pref_v", 1),
        },
        "training": {
            "numb_steps": strategy.get("numb_steps", 250000),
            "disp_freq": strategy.get("disp_freq", 100),
            "save_freq": strategy.get("save_freq", 10000),
            "seed": 1,
            "disp_training": True,
            "time_training": True,
            "profiling": False,
        },
    }


def _model_devi_jobs(
    system_profile: dict[str, Any],
    strategy: dict[str, Any],
) -> list[dict[str, Any]]:
    explicit = strategy.get("model_devi_jobs")
    if isinstance(explicit, list) and explicit:
        return copy.deepcopy(explicit)

    target_conditions = system_profile.get("target_conditions") or {}
    temps = _as_list(target_conditions.get("temperature_k") or strategy.get("temps") or [300])
    press = _as_list(target_conditions.get("pressure_bar") or strategy.get("press") or [1.0])
    ensemble = _as_list(target_conditions.get("ensemble") or strategy.get("ensemble") or ["nvt"])[0]
    nsteps_schedule = _as_list(strategy.get("nsteps_schedule") or [5000, 10000, 20000])
    trj_freq_schedule = _as_list(strategy.get("trj_freq_schedule") or [50, 100, 100])
    sys_count = len(system_profile.get("exploration_structures") or [])
    sys_idx = list(range(sys_count)) if sys_count else [0]

    jobs: list[dict[str, Any]] = []
    for idx, nsteps in enumerate(nsteps_schedule):
        jobs.append(
            {
                "_idx": f"{idx:02d}",
                "sys_idx": sys_idx,
                "temps": temps,
                "press": press,
                "trj_freq": trj_freq_schedule[min(idx, len(trj_freq_schedule) - 1)],
                "nsteps": nsteps,
                "ensemble": ensemble,
            }
        )
    return jobs


def build_dpgen_param(
    *,
    system_profile_path: Path,
    strategy_config_path: Path,
    output_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    """Build a DP-GEN param JSON from normalized profile files."""
    system_profile = load_json_or_yaml(system_profile_path)
    strategy = load_json_or_yaml(strategy_config_path)
    if not isinstance(system_profile, dict):
        raise ValueError("system_profile must be a JSON/YAML object.")
    if not isinstance(strategy, dict):
        raise ValueError("strategy_config must be a JSON/YAML object.")

    elements = list(system_profile.get("elements") or strategy.get("type_map") or [])
    if not elements:
        raise ValueError("system_profile.elements is required.")

    base_payload: dict[str, Any] = {}
    base_param_path = strategy.get("base_param_path")
    if isinstance(base_param_path, str) and base_param_path.strip():
        base_path = Path(base_param_path).expanduser()
        if not base_path.is_absolute():
            base_path = strategy_config_path.parent / base_path
        loaded_base = load_json_or_yaml(base_path)
        if not isinstance(loaded_base, dict):
            raise ValueError("strategy_config.base_param_path must point to a JSON/YAML object.")
        base_payload = copy.deepcopy(loaded_base)

    init_data = list(system_profile.get("initial_data") or [])
    exploration = system_profile.get("exploration_structures") or []
    if exploration and all(isinstance(item, str) for item in exploration):
        sys_configs = [[item] for item in exploration]
    else:
        sys_configs = exploration
    if not isinstance(sys_configs, list) or not sys_configs:
        sys_configs = [[]]

    generated = {
        "default_training_param": strategy.get("default_training_param")
        or _default_training_param(elements, strategy),
        "init_data_prefix": strategy.get("init_data_prefix", "./"),
        "init_data_sys": init_data,
        "init_batch_size": strategy.get("init_batch_size") or _repeat_auto(len(init_data)),
        "sys_format": strategy.get("sys_format", "vasp/poscar"),
        "sys_configs_prefix": strategy.get("sys_configs_prefix", "./"),
        "sys_configs": sys_configs,
        "sys_batch_size": strategy.get("sys_batch_size") or _repeat_auto(len(sys_configs)),
        "numb_models": strategy.get("numb_models", 4),
        "mass_map": strategy.get("mass_map", "auto"),
        "type_map": elements,
        "model_devi_dt": strategy.get("model_devi_dt", 0.001),
        "model_devi_skip": strategy.get("model_devi_skip", 0),
        "model_devi_f_trust_lo": strategy.get("model_devi_f_trust_lo", 0.05),
        "model_devi_f_trust_hi": strategy.get("model_devi_f_trust_hi", 0.15),
        "model_devi_nopbc": strategy.get("model_devi_nopbc", False),
        "model_devi_merge_traj": strategy.get("model_devi_merge_traj", True),
        "model_devi_clean_traj": strategy.get("model_devi_clean_traj", False),
        "model_devi_jobs": _model_devi_jobs(system_profile, strategy),
        "fp_task_max": strategy.get("fp_task_max", 100),
        "fp_task_min": strategy.get("fp_task_min", 5),
        "shuffle_poscar": strategy.get("shuffle_poscar", False),
        "detailed_report_make_fp": strategy.get("detailed_report_make_fp", True),
        "fp_style": strategy.get("fp_style", "vasp"),
    }
    payload = _deep_update(base_payload, generated) if base_payload else generated
    for key in (
        "fp_pp_path",
        "fp_pp_files",
        "fp_incar",
        "fp_kpt",
        "external_input_path",
        "model_devi_activation_func",
        "training_reuse_iter",
        "training_reuse_old_ratio",
        "model_devi_engine",
        "model_devi_template",
        "ratio_failed",
        "ratio_failure",
        "fp_style",
        "external_input_path",
    ):
        if key in strategy:
            payload[key] = strategy[key]
    if isinstance(strategy.get("param_overrides"), dict):
        _deep_update(payload, strategy["param_overrides"])

    _write_json(output_path, payload)
    artifacts = [
        artifact(system_profile_path, "config"),
        artifact(strategy_config_path, "config"),
        artifact(output_path, "config"),
    ]
    if isinstance(base_param_path, str) and base_param_path.strip():
        base_path = Path(base_param_path).expanduser()
        if not base_path.is_absolute():
            base_path = strategy_config_path.parent / base_path
        if base_path.is_file():
            artifacts.append(artifact(base_path, "config"))
    warnings: list[str] = []
    if not init_data:
        warnings.append("system_profile.initial_data is empty; DP-GEN training may fail without initial data.")
    if sys_configs == [[]]:
        warnings.append("system_profile.exploration_structures is empty; generated sys_configs is a placeholder.")
    return payload, artifacts, warnings


def _stage_machine(stage: str, profile: dict[str, Any]) -> dict[str, Any]:
    command = profile.get("command") or {"train": "dp", "model_devi": "lmp", "fp": "vasp_std"}.get(stage, "")
    machine = {
        "batch_type": profile.get("batch_type", "Shell"),
        "local_root": profile.get("local_root", "./"),
        "remote_root": profile.get("remote_root", f"./remote/{stage}"),
        "context_type": profile.get("context_type", "local"),
        "clean_asynchronously": profile.get("clean_asynchronously", False),
    }
    if "remote_profile" in profile:
        machine["remote_profile"] = copy.deepcopy(profile["remote_profile"])
    resources = {
        "number_node": profile.get("number_node", 1),
        "cpu_per_node": profile.get("cpu_per_node", 1),
        "gpu_per_node": profile.get("gpu_per_node", 0 if stage == "fp" else 1),
        "queue_name": profile.get("queue_name", ""),
        "group_size": profile.get("group_size", 1),
        "para_deg": profile.get("para_deg", 1),
        "source_list": profile.get("source_list", []),
        "envs": profile.get("envs", {}),
        "prepend_script": profile.get("prepend_script", []),
        "append_script": profile.get("append_script", []),
        "wait_time": profile.get("wait_time", 0),
        "batch_type": profile.get("batch_type", "Shell"),
    }
    return {
        "command": command,
        "machine": machine,
        "resources": resources,
        "user_forward_files": profile.get("user_forward_files", []),
        "user_backward_files": profile.get("user_backward_files", []),
    }


def build_dpgen_machine(
    *,
    machine_profile_path: Path,
    output_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[str]]:
    """Build a DP-GEN machine JSON from a machine profile."""
    profile = load_json_or_yaml(machine_profile_path)
    if not isinstance(profile, dict):
        raise ValueError("machine_profile must be a JSON/YAML object.")

    payload = {
        "api_version": profile.get("api_version", "1.0"),
        "deepmd_version": profile.get("deepmd_version", "2"),
        "train": _stage_machine("train", profile.get("train") or {}),
        "model_devi": _stage_machine("model_devi", profile.get("model_devi") or {}),
        "fp": _stage_machine("fp", profile.get("fp") or {}),
    }
    redacted, secret_findings = redact_mapping(payload)
    _write_json(output_path, payload)
    redacted_path = output_path.with_name(output_path.stem + ".redacted.json")
    _write_json(redacted_path, redacted)
    artifacts = [
        artifact(machine_profile_path, "config"),
        artifact(output_path, "config"),
        artifact(redacted_path, "config"),
    ]
    warnings = [f"machine profile produced secret-like field: {path}" for path in secret_findings]
    return payload, redacted, artifacts, warnings
