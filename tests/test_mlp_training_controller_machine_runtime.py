from __future__ import annotations

import json
import sys
from pathlib import Path

MCP_SRC = Path(__file__).resolve().parents[1] / "mlpcopilot" / "mcps" / "mlp_training_controller_mcp" / "src"
sys.path.insert(0, str(MCP_SRC))

from mlp_training_controller_mcp.backends.dpgen import DPGenBackend  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _script(path: Path, text: str) -> None:
    _write(path, text)
    path.chmod(path.stat().st_mode | 0o111)


def test_validate_machine_runtime_probe_success_and_report(tmp_path: Path) -> None:
    _script(
        tmp_path / "wrappers" / "ok.sh",
        "#!/usr/bin/env bash\nset -euo pipefail\necho ok \"$@\"\n",
    )
    machine = tmp_path / "machine.json"
    _write(
        machine,
        json.dumps(
            {
                "train": {"command": "bash wrappers/ok.sh"},
                "model_devi": {"command": "bash wrappers/ok.sh"},
                "fp": {"command": "bash wrappers/ok.sh -i input.inp -o output.out"},
            }
        ),
    )

    payload = json.loads(DPGenBackend().validate_machine_runtime(machine_path=str(machine), project_path=str(tmp_path)))

    assert payload["status"] == "success"
    assert payload["metrics"]["probes_run"] == 3
    report = tmp_path / "machine_runtime_validation.json"
    assert report.is_file()
    report_payload = json.loads(report.read_text(encoding="utf-8"))
    assert report_payload["probes"][2]["command"] == "bash wrappers/ok.sh --version"


def test_validate_training_inputs_rejects_non_current_machine_stage_shape(tmp_path: Path) -> None:
    param = tmp_path / "param.json"
    machine = tmp_path / "machine.json"
    _write(param, json.dumps({"type_map": ["H"], "mass_map": [1.0]}))
    _write(
        machine,
        json.dumps(
            {
                "api_version": "1.0",
                "train": [{"command": "dp", "machine": {}, "resources": {}}],
                "model_devi": {"command": "lmp", "machine": {}, "resources": {}},
                "fp": {"command": "vasp_std", "machine": {}, "resources": {}},
            }
        ),
    )

    payload = json.loads(
        DPGenBackend().validate_training_inputs(
            param_path=str(param),
            machine_path=str(machine),
            project_path=str(tmp_path),
        )
    )

    assert payload["status"] == "failed"
    assert any("supports only the current DP-GEN machine schema" in item for item in payload["errors"])
    assert any("replace \"train\": [{...}] with \"train\": {...}" in item for item in payload["errors"])


def test_validate_machine_runtime_exact_timeout(tmp_path: Path) -> None:
    _script(
        tmp_path / "wrappers" / "slow.sh",
        "#!/usr/bin/env bash\nset -euo pipefail\nsleep 2\n",
    )
    machine = tmp_path / "machine.json"
    _write(machine, json.dumps({"train": {"command": "bash wrappers/slow.sh"}}))

    payload = json.loads(
        DPGenBackend().validate_machine_runtime(
            machine_path=str(machine),
            project_path=str(tmp_path),
            stages="train",
            timeout_seconds=1,
            exact=True,
        )
    )

    assert payload["status"] == "failed"
    report_payload = json.loads((tmp_path / "machine_runtime_validation.json").read_text(encoding="utf-8"))
    assert report_payload["probes"][0]["timed_out"] is True


def test_validate_machine_runtime_truncates_logs(tmp_path: Path) -> None:
    _script(
        tmp_path / "wrappers" / "log.sh",
        "#!/usr/bin/env bash\nset -euo pipefail\nprintf '%0800d\\n' 0\n",
    )
    machine = tmp_path / "machine.json"
    _write(machine, json.dumps({"train": {"command": "bash wrappers/log.sh"}}))

    payload = json.loads(
        DPGenBackend().validate_machine_runtime(
            machine_path=str(machine),
            project_path=str(tmp_path),
            stages="train",
            max_log_chars=120,
        )
    )

    assert payload["status"] == "success"
    report_payload = json.loads((tmp_path / "machine_runtime_validation.json").read_text(encoding="utf-8"))
    assert "[truncated]" in report_payload["probes"][0]["stdout"]
