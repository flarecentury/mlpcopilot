"""DP-GEN backend facade for the MLP training controller MCP."""

from __future__ import annotations

from importlib import import_module
from typing import Any

DPGEN_BACKEND_NAME = "dpgen"


class DPGenBackend:
    """Thin facade that routes training-controller operations to DP-GEN modules."""

    backend = DPGEN_BACKEND_NAME

    def _call(self, module_name: str, function_name: str, *args: Any, **kwargs: Any) -> str:
        module = import_module(f"{__package__}.{module_name}")
        function = getattr(module, function_name)
        return function(self.backend, *args, **kwargs)

    def generate_training_param(self, **kwargs: Any) -> str:
        return self._call("dpgen_generation", "generate_training_param", **kwargs)

    def generate_training_machine(self, **kwargs: Any) -> str:
        return self._call("dpgen_generation", "generate_training_machine", **kwargs)

    def inspect_training_project(self, project_path: str) -> str:
        return self._call("dpgen_read", "inspect_training_project", project_path)

    def validate_training_inputs(self, **kwargs: Any) -> str:
        return self._call("dpgen_validation", "validate_training_inputs", **kwargs)

    def validate_machine_runtime(self, **kwargs: Any) -> str:
        return self._call("dpgen_validation", "validate_machine_runtime", **kwargs)

    def get_training_status(self, project_path: str) -> str:
        return self._call("dpgen_read", "get_training_status", project_path)

    def list_training_iterations(self, project_path: str) -> str:
        return self._call("dpgen_read", "list_training_iterations", project_path)

    def inspect_training_iteration(self, project_path: str, iteration: int) -> str:
        return self._call("dpgen_read", "inspect_training_iteration", project_path, iteration)

    def collect_training_logs(self, project_path: str, max_lines: int = 80) -> str:
        return self._call("dpgen_read", "collect_training_logs", project_path, max_lines=max_lines)

    def analyze_training_failure(self, project_path: str, max_lines: int = 200) -> str:
        return self._call("dpgen_read", "analyze_training_failure", project_path, max_lines=max_lines)

    def build_training_run_report(self, project_path: str, output_path: str | None = None) -> str:
        return self._call("dpgen_read", "build_training_run_report", project_path, output_path=output_path)

    def get_controller_state(self, **kwargs: Any) -> str:
        return self._call("dpgen_process", "get_controller_state", **kwargs)

    def start_training_run(self, **kwargs: Any) -> str:
        return self._call("dpgen_process", "start_training_run", **kwargs)

    def run_training_controller(self, **kwargs: Any) -> str:
        return self._call("dpgen_process", "run_training_controller", **kwargs)

    def stop_training_run(self, **kwargs: Any) -> str:
        return self._call("dpgen_process", "stop_training_run", **kwargs)

    def resume_training_run(self, **kwargs: Any) -> str:
        return self._call("dpgen_process", "resume_training_run", **kwargs)

    def plan_training_reset(self, **kwargs: Any) -> str:
        return self._call("dpgen_reset", "plan_training_reset", **kwargs)

    def plan_training_rewind(self, **kwargs: Any) -> str:
        return self._call("dpgen_reset", "plan_training_rewind", **kwargs)

    def reset_training_run(self, **kwargs: Any) -> str:
        return self._call("dpgen_reset", "reset_training_run", **kwargs)

    def apply_training_rewind(self, **kwargs: Any) -> str:
        return self._call("dpgen_reset", "apply_training_rewind", **kwargs)

    def rerun_failed_stage(self, **kwargs: Any) -> str:
        return self._call("dpgen_reset", "rerun_failed_stage", **kwargs)

    def list_dispatcher_jobs(self, **kwargs: Any) -> str:
        return self._call("dpgen_jobs", "list_dispatcher_jobs", **kwargs)

    def inspect_dispatcher_job(self, **kwargs: Any) -> str:
        return self._call("dpgen_jobs", "inspect_dispatcher_job", **kwargs)

    def cancel_remote_jobs(self, **kwargs: Any) -> str:
        return self._call("dpgen_jobs", "cancel_remote_jobs", **kwargs)

    def cancel_scheduler_jobs(self, **kwargs: Any) -> str:
        return self._call("dpgen_jobs", "cancel_scheduler_jobs", **kwargs)

    def snapshot_training_state(self, **kwargs: Any) -> str:
        return self._call("dpgen_evidence", "snapshot_training_state", **kwargs)

    def collect_iteration_evidence(self, **kwargs: Any) -> str:
        return self._call("dpgen_evidence", "collect_iteration_evidence", **kwargs)

    def plan_machine_update(self, **kwargs: Any) -> str:
        return self._call("dpgen_config_updates", "plan_machine_update", **kwargs)

    def plan_config_update(self, **kwargs: Any) -> str:
        return self._call("dpgen_config_updates", "plan_config_update", **kwargs)

    def apply_machine_update(self, **kwargs: Any) -> str:
        return self._call("dpgen_config_updates", "apply_machine_update", **kwargs)

    def apply_config_update(self, **kwargs: Any) -> str:
        return self._call("dpgen_config_updates", "apply_config_update", **kwargs)

    def plan_param_update(self, **kwargs: Any) -> str:
        return self._call("dpgen_config_updates", "plan_param_update", **kwargs)

    def apply_param_update(self, **kwargs: Any) -> str:
        return self._call("dpgen_config_updates", "apply_param_update", **kwargs)
