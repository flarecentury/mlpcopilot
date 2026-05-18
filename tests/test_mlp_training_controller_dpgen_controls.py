from __future__ import annotations

import json
import sys
import time
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


def _project(tmp_path: Path) -> Path:
    _write(tmp_path / "param.json", "{}\n")
    _write(tmp_path / "machine.json", "{}\n")
    return tmp_path


def test_start_stop_training_run_with_fake_dpgen(tmp_path: Path) -> None:
    project = _project(tmp_path)
    fake_dpgen = tmp_path / "fake_dpgen.sh"
    _script(
        fake_dpgen,
        "#!/usr/bin/env bash\n"
        "trap 'exit 0' TERM INT\n"
        "echo fake-dpgen \"$@\"\n"
        "while true; do sleep 1; done\n",
    )

    start = json.loads(
        DPGenBackend().run_training_controller(
            project_path=str(project),
            run_id="run_fake",
            dpgen_command=f"bash {fake_dpgen}",
        )
    )
    try:
        assert start["status"] == "success"
        state_path = project / "runs" / "run_fake" / "training_controller_state.json"
        manifest_path = project / "runs" / "run_fake" / "manifest.json"
        assert state_path.is_file()
        assert manifest_path.is_file()
        assert any(item["type"] == "manifest" and item["path"] == str(manifest_path) for item in start["artifacts"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["source"] == "mcp:trainingController:start_training_run"
        assert manifest["inputs"][0]["path"] == str(project / "param.json")
        assert manifest["metrics"][0]["name"] == "controller_status"
        assert manifest["metrics"][0]["value"] == "running"
        assert manifest["metadata"]["events"][0]["operation"] == "start_training_run"

        state = json.loads(DPGenBackend().get_controller_state(project_path=str(project), run_id="run_fake"))
        assert state["status"] == "success"
        assert state["metrics"]["state"]["status"] == "running"

        stop = json.loads(DPGenBackend().stop_training_run(project_path=str(project), run_id="run_fake"))
        assert stop["status"] == "success"
        assert stop["metrics"]["state"]["status"] == "stop_requested"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert any(item["name"] == "controller_status" and item["value"] == "stop_requested" for item in manifest["metrics"])
        assert [item["operation"] for item in manifest["metadata"]["events"]] == [
            "start_training_run",
            "stop_training_run",
        ]
    finally:
        time.sleep(0.2)


def test_plan_and_apply_training_reset(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _write(project / "record.dpgen", "3 7\n")
    (project / "iter.000004").mkdir()

    plan = json.loads(
        DPGenBackend().plan_training_reset(
            project_path=str(project),
            target_iteration=3,
            target_stage=4,
            mode="hard",
        )
    )
    assert plan["status"] == "success"
    assert plan["metrics"]["hard_mode_iter_dirs_to_move"] == [str(project / "iter.000004")]
    assert plan["metrics"]["hard_mode_iter_dirs_to_archive"] == [str(project / "iter.000004")]
    assert plan["metrics"]["preservation_policy"]["requires_user_confirmation"] is True
    assert "does not delete" in " ".join(plan["warnings"])

    applied = json.loads(
        DPGenBackend().reset_training_run(
            project_path=str(project),
            target_iteration=3,
            target_stage=4,
            mode="hard",
        )
    )
    assert applied["status"] == "success"
    assert (project / "record.dpgen").read_text(encoding="utf-8") == "3 4\n"
    assert not (project / "iter.000004").exists()
    backup_run_id = Path(applied["metrics"]["backup_dir"]).name
    moved = Path(applied["metrics"]["backup_dir"]) / "moved_iter_dirs" / "iter.000004"
    snapshot = Path(applied["metrics"]["backup_dir"]) / "state_snapshot_before.json"
    assert moved.is_dir()
    assert snapshot.is_file()
    assert any(item.get("kind") == "pre_rewind_snapshot" for item in applied["metrics"]["backups"])
    assert any(item.get("kind") == "archived_iter_dir" for item in applied["metrics"]["backups"])
    manifest_path = project / "runs" / backup_run_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["source"] == "mcp:trainingController:reset_training_run"
    assert manifest["lineage"]["target_record"]["stage"] == 4
    assert any(item["type"] == "manifest" and item["path"] == str(manifest_path) for item in applied["artifacts"])


def test_plan_and_apply_training_rewind_previous_stage(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _write(project / "record.dpgen", "3 7\n")
    (project / "iter.000004").mkdir()

    plan = json.loads(DPGenBackend().plan_training_rewind(project_path=str(project)))

    assert plan["status"] == "success"
    assert plan["metrics"]["target_record"]["iteration"] == 3
    assert plan["metrics"]["target_record"]["stage"] == 6
    assert plan["metrics"]["rewind_target"] == "previous_stage"
    assert plan["metrics"]["soft_mode_iter_dirs_preserved"] == [str(project / "iter.000004")]
    assert plan["metrics"]["preservation_policy"]["default_mode"] == "soft"
    assert "Soft mode preserves" in " ".join(plan["warnings"])

    applied = json.loads(DPGenBackend().apply_training_rewind(project_path=str(project)))
    assert applied["status"] == "success"
    assert (project / "record.dpgen").read_text(encoding="utf-8") == "3 6\n"
    assert (project / "iter.000004").is_dir()
    assert (Path(applied["metrics"]["backup_dir"]) / "state_snapshot_before.json").is_file()
    manifest_path = project / "runs" / Path(applied["metrics"]["backup_dir"]).name / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["source"] == "mcp:trainingController:apply_training_rewind"
    assert manifest["metadata"]["events"][0]["rewind_target"] == "previous_stage"


def test_apply_training_rewind_refreshes_mlpcopilot_display_projection(tmp_path: Path) -> None:
    from mlpcopilot.plugins.dpgen_adapter import project_dpgen_run
    from mlpcopilot.runtime.workspace import create_mlp_project, create_mlp_run

    workspace = tmp_path / "workspace"
    project = create_mlp_project(workspace, name="FeCH", project_id="proj_rewind")
    run = create_mlp_run(workspace, project["project_id"], run_id="run_local")
    backend = workspace / "projects" / project["project_id"] / "runs" / run["run_id"] / "backend" / "dpgen"
    _write(backend / "param.json", "{}\n")
    _write(backend / "machine.json", "{}\n")
    _write(backend / "record.dpgen", "21 0\n")
    (backend / "iter.000002" / "00.train").mkdir(parents=True)
    (backend / "iter.000021" / "00.train").mkdir(parents=True)
    project_dpgen_run(workspace, project["project_id"], run["run_id"])

    stale_companion = json.loads(
        (
            workspace
            / "projects"
            / project["project_id"]
            / "runs"
            / run["run_id"]
            / "ui"
            / "companion.display.json"
        ).read_text(encoding="utf-8")
    )
    assert "iter.000021 stage0 make_train" in stale_companion["summary"]

    applied = json.loads(
        DPGenBackend().apply_training_rewind(
            project_path=str(backend),
            target="explicit",
            target_iteration=2,
            target_stage=0,
        )
    )

    assert applied["status"] == "success"
    refresh = applied["metrics"]["mlpcopilot_projection_refresh"]
    assert refresh["status"] == "success"
    assert refresh["refreshed"][0]["project_id"] == project["project_id"]
    assert refresh["refreshed"][0]["run_id"] == run["run_id"]

    run_dir = workspace / "projects" / project["project_id"] / "runs" / run["run_id"]
    companion = json.loads((run_dir / "ui" / "companion.display.json").read_text(encoding="utf-8"))
    assert "iter.000002 stage0 make_train" in companion["summary"]
    artifacts = json.loads((run_dir / "ui" / "artifacts.display.json").read_text(encoding="utf-8"))
    kv_block = next(block for block in artifacts["body"] if block.get("type") == "key_values")
    assert {"key": "Focus", "value": "iter_000002"} in kv_block["items"]
    table = next(block for block in artifacts["body"] if block.get("type") == "table")
    assert any(row[0] == "iter.000002/00.train" for row in table["rows"])
    assert all("iter.000021" not in row[0] for row in table["rows"])


def test_training_status_exposes_fresh_record_source_and_next_stage(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _write(project / "record.dpgen", "2 8\n")
    (project / "iter.000002" / "02.fp").mkdir(parents=True)

    status = json.loads(DPGenBackend().get_training_status(project_path=str(project)))

    assert status["status"] == "success"
    assert status["metrics"]["current_iteration"] == 2
    assert status["metrics"]["current_stage"] == 8
    assert status["metrics"]["stage_name"] == "post_fp"
    assert status["metrics"]["next_iteration"] == 3
    assert status["metrics"]["next_stage"] == 0
    assert status["metrics"]["next_stage_name"] == "make_train"
    assert status["metrics"]["status_source"] == "record.dpgen + iteration directories"
    assert status["metrics"]["record_path"] == str(project / "record.dpgen")
    assert status["metrics"]["record_sha256"]
    assert status["metrics"]["queried_at"]


def test_snapshot_training_state_records_source_and_next_record(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _write(project / "record.dpgen", "1 3\n")
    snapshot_path = project / "reports" / "snapshot.json"

    payload = json.loads(
        DPGenBackend().snapshot_training_state(
            project_path=str(project),
            output_path=str(snapshot_path),
        )
    )

    assert payload["status"] == "success"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["record"]["iteration"] == 1
    assert snapshot["record"]["stage"] == 3
    assert snapshot["next_record"]["iteration"] == 1
    assert snapshot["next_record"]["stage"] == 4
    assert snapshot["next_record"]["stage_name"] == "run_model_devi"
    assert snapshot["status_source"] == "record.dpgen + iteration directories + controller state files"


def test_dispatcher_job_listing_and_inspection(tmp_path: Path) -> None:
    project = _project(tmp_path)
    job = project / "iter.000001" / "02.fp" / "task.000001" / "job.json"
    _write(job, json.dumps({"hostname": "node1", "password": "secret"}))
    _write(job.parent / "fp.log", "line1\nline2\n")

    listed = json.loads(DPGenBackend().list_dispatcher_jobs(project_path=str(project)))

    assert listed["status"] == "success"
    assert listed["metrics"]["total_jobs"] == 1
    job_id = listed["metrics"]["jobs"][0]["id"]

    inspected = json.loads(DPGenBackend().inspect_dispatcher_job(project_path=str(project), job_ref=job_id))

    assert inspected["status"] == "success"
    assert inspected["metrics"]["stage"] == "fp"
    assert inspected["metrics"]["job"]["password"] == "<redacted>"
    assert inspected["metrics"]["logs"][0]["tail"] == ["line1", "line2"]


def test_plan_and_apply_machine_update_redacts_and_backs_up(tmp_path: Path) -> None:
    machine = tmp_path / "machine.json"
    _write(
        machine,
        json.dumps(
            {
                "train": {
                    "command": "old",
                    "machine": {"remote_profile": {"password": "secret"}},
                }
            }
        ),
    )

    plan = json.loads(
        DPGenBackend().plan_machine_update(
            machine_path=str(machine),
            updates_json=json.dumps({"train": {"command": "new"}}),
        )
    )
    assert plan["status"] == "success"
    assert plan["metrics"]["after_preview"]["train"]["machine"]["remote_profile"]["password"] == "<redacted>"

    applied = json.loads(
        DPGenBackend().apply_machine_update(
            machine_path=str(machine),
            updates_json=json.dumps({"train": {"command": "new"}}),
        )
    )
    assert applied["status"] == "success"
    assert json.loads(machine.read_text(encoding="utf-8"))["train"]["command"] == "new"
    assert applied["metrics"]["backup"]["backup_path"]


def test_plan_and_apply_config_update_for_param(tmp_path: Path) -> None:
    param = tmp_path / "param.json"
    _write(param, json.dumps({"numb_models": 2}))

    plan = json.loads(
        DPGenBackend().plan_config_update(
            config_kind="param",
            config_path=str(param),
            updates_json=json.dumps({"numb_models": 4}),
        )
    )
    assert plan["status"] == "success"
    assert plan["metrics"]["config_kind"] == "param"
    assert plan["metrics"]["changes"] == 1

    applied = json.loads(
        DPGenBackend().apply_config_update(
            config_kind="param",
            config_path=str(param),
            updates_json=json.dumps({"numb_models": 4}),
        )
    )
    assert applied["status"] == "success"
    assert json.loads(param.read_text(encoding="utf-8"))["numb_models"] == 4


def test_cancel_scheduler_jobs_runs_standard_mcp_tool(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path)
    calls = []

    def _fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return type("Completed", (), {"returncode": 0, "stdout": "cancelled\n", "stderr": ""})()

    monkeypatch.setattr("mlp_training_controller_mcp.backends.dpgen_jobs.subprocess.run", _fake_run)

    payload = json.loads(
        DPGenBackend().cancel_scheduler_jobs(
            project_path=str(project),
            scheduler="slurm",
            job_ids_json=json.dumps(["12345"]),
        )
    )

    assert payload["status"] == "success"
    assert payload["metrics"]["command"] == ["scancel", "12345"]
    assert calls[0][0] == ["scancel", "12345"]
