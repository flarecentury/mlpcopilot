import json
import time

from mlpcopilot.runtime.workspace import MLPCOPILOT_DIRS, sync_mlpcopilot_workspace


def test_sync_mlpcopilot_workspace_creates_schema(tmp_path) -> None:
    added = sync_mlpcopilot_workspace(tmp_path, silent=True)

    assert "PROJECT.md" in added
    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / "PROJECT.md").exists()
    assert (tmp_path / "TOOLS.md").exists()
    agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "~/.mlpcopilot/scratch/" in agents
    assert "Task Intake and Alignment" in agents
    assert "Persist the agreed goal, plan, and active project/run pointer" in agents
    tools = (tmp_path / "TOOLS.md").read_text(encoding="utf-8")
    assert "Scratch Boundary" in tools
    assert "agentic-file-search" in tools
    assert "workstate" in tools
    assert "my (read-only" in tools
    for dirname in MLPCOPILOT_DIRS:
        assert (tmp_path / dirname).is_dir()

    assert not (tmp_path / "capabilities").exists()
    assert not (tmp_path / "capabilities" / "mcp.json").exists()
    assert (tmp_path / "approvals" / "pending.jsonl").exists()
    assert (tmp_path / "approvals" / "decisions.jsonl").exists()


def test_sync_mlpcopilot_workspace_does_not_overwrite_existing_project(tmp_path) -> None:
    project = tmp_path / "PROJECT.md"
    project.write_text("custom project\n", encoding="utf-8")

    sync_mlpcopilot_workspace(tmp_path, silent=True)

    assert project.read_text(encoding="utf-8") == "custom project\n"


def test_sync_mlpcopilot_workspace_preserves_stale_capabilities_files(tmp_path) -> None:
    capabilities = tmp_path / "capabilities"
    capabilities.mkdir(parents=True)
    (capabilities / "mcp.json").write_text("{}\n", encoding="utf-8")
    (capabilities / "skills.json").write_text("{}\n", encoding="utf-8")

    sync_mlpcopilot_workspace(tmp_path, silent=True)

    assert (capabilities / "mcp.json").exists()
    assert (capabilities / "skills.json").exists()


def test_sync_mlpcopilot_workspace_preserves_checkpoint_only_capabilities_dir(tmp_path) -> None:
    capabilities = tmp_path / "capabilities"
    checkpoint = capabilities / ".ipynb_checkpoints" / "skills-checkpoint.json"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text("{}\n", encoding="utf-8")

    sync_mlpcopilot_workspace(tmp_path, silent=True)

    assert checkpoint.exists()


def test_sync_mlpcopilot_workspace_preserves_unknown_capabilities_files(tmp_path) -> None:
    capabilities = tmp_path / "capabilities"
    custom = capabilities / "custom.json"
    custom.parent.mkdir(parents=True)
    custom.write_text("{}\n", encoding="utf-8")

    sync_mlpcopilot_workspace(tmp_path, silent=True)

    assert custom.exists()


def test_project_run_schema_and_dpgen_projector(tmp_path) -> None:
    from mlpcopilot.config.schema import Config
    from mlpcopilot.plugins.dpgen_adapter import project_dpgen_run
    from mlpcopilot.runtime.artifact_records import (
        artifact_attach_context,
        artifact_lineage,
        find_run_artifact,
    )
    from mlpcopilot.runtime.tui.layouts.render_data import collect_tui_render_data
    from mlpcopilot.runtime.workspace import create_mlp_project, create_mlp_run

    project = create_mlp_project(
        tmp_path,
        name="FeCH active learning",
        target_use_case="compressed liquid coverage",
        project_id="proj_test",
    )
    run = create_mlp_run(tmp_path, "proj_test", run_id="run_test")
    backend = tmp_path / "projects" / "proj_test" / "runs" / "run_test" / "backend" / "dpgen"
    backend.mkdir(parents=True, exist_ok=True)
    (backend / "param.json").write_text("{}\n", encoding="utf-8")
    (backend / "machine.json").write_text("{}\n", encoding="utf-8")
    (backend / "record.dpgen").write_text("0 0\n0 1\n0 5\n", encoding="utf-8")
    (backend / "iter.000000" / "00.train" / "000").mkdir(parents=True)
    (backend / "iter.000000" / "00.train" / "000" / "lcurve.out").write_text("step loss\n", encoding="utf-8")
    (backend / "iter.000000" / "01.model_devi").mkdir(parents=True)
    (backend / "iter.000000" / "02.fp" / "task.000.000000").mkdir(parents=True)
    (backend / "iter.000000" / "02.fp" / "candidate.out").write_text("1\n", encoding="utf-8")

    summary = project_dpgen_run(tmp_path, project["project_id"], run["run_id"])

    assert summary["record_entries"] == 3
    assert summary["detected_iterations"] == 1
    assert summary["next_expected"]["phase"] == "label.prepare"
    run_state = json.loads(
        (tmp_path / "projects" / "proj_test" / "runs" / "run_test" / "run_state.json").read_text(encoding="utf-8")
    )
    assert run_state["last_completed"]["phase"] == "explore.collect"
    artifacts_display = json.loads(
        (tmp_path / "projects" / "proj_test" / "runs" / "run_test" / "ui" / "artifacts.display.json").read_text(
            encoding="utf-8"
        )
    )
    assert artifacts_display["title"] == "DP-GEN Artifacts"
    assert artifacts_display["body"]

    artifact = find_run_artifact(tmp_path, "proj_test", "run_test", "record.dpgen")
    assert artifact["kind"] == "run_record"
    assert artifact_lineage(tmp_path, "proj_test", "run_test", artifact["artifact_id"])["parents"] == []
    attach = artifact_attach_context(tmp_path, "proj_test", "run_test", artifact["artifact_id"])
    assert attach["path"].endswith("record.dpgen")

    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    data = collect_tui_render_data(config)
    assert data.artifacts_display is not None
    assert data.companion_display is not None
    assert data.artifacts_display["title"] == "DP-GEN Artifacts"

    artifacts_display["revision"] = 99
    artifacts_display["body"] = [{"type": "table", "columns": ["Priority", "Signal"], "rows": [["updated", "-"]]}]
    (
        tmp_path / "projects" / "proj_test" / "runs" / "run_test" / "ui" / "artifacts.display.json"
    ).write_text(json.dumps(artifacts_display), encoding="utf-8")
    refreshed = collect_tui_render_data(config)
    assert refreshed.artifacts_display is not None
    assert refreshed.artifacts_display["revision"] == 99
    assert refreshed.artifacts_display["body"][0]["rows"][0][0] == "updated"


def test_tui_render_data_refreshes_stale_dpgen_display_on_record_change(tmp_path) -> None:
    from mlpcopilot.config.schema import Config
    from mlpcopilot.plugins.dpgen_adapter import project_dpgen_run
    from mlpcopilot.runtime.tui.layouts.render_data import collect_tui_render_data
    from mlpcopilot.runtime.workspace import create_mlp_project, create_mlp_run

    project = create_mlp_project(tmp_path, name="FeCH", project_id="proj_watch")
    run = create_mlp_run(tmp_path, project["project_id"], run_id="run_watch")
    backend = tmp_path / "projects" / project["project_id"] / "runs" / run["run_id"] / "backend" / "dpgen"
    record = backend / "record.dpgen"
    (backend / "param.json").write_text("{}\n", encoding="utf-8")
    (backend / "machine.json").write_text("{}\n", encoding="utf-8")
    record.write_text("21 0\n", encoding="utf-8")
    (backend / "iter.000002" / "00.train").mkdir(parents=True)
    (backend / "iter.000021" / "00.train").mkdir(parents=True)
    project_dpgen_run(tmp_path, project["project_id"], run["run_id"])

    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    stale = collect_tui_render_data(config)
    assert stale.companion_display is not None
    assert "iter.000021 stage0 make_train" in stale.companion_display["summary"]

    time.sleep(0.01)
    record.write_text("2 0\n", encoding="utf-8")
    refreshed = collect_tui_render_data(config)

    assert refreshed.companion_display is not None
    assert "iter.000002 stage0 make_train" in refreshed.companion_display["summary"]
    assert refreshed.artifacts_display is not None
    kv_block = next(block for block in refreshed.artifacts_display["body"] if block.get("type") == "key_values")
    assert {"key": "Focus", "value": "iter_000002"} in kv_block["items"]
    table = next(block for block in refreshed.artifacts_display["body"] if block.get("type") == "table")
    assert any(row[0] == "iter.000002/00.train" for row in table["rows"])
    assert all("iter.000021" not in row[0] for row in table["rows"])


def test_tui_render_data_prefers_session_active_project_pointer(tmp_path) -> None:
    from mlpcopilot.config.schema import Config
    from mlpcopilot.runtime.tui.layouts.render_data import collect_tui_render_data
    from mlpcopilot.runtime.workspace import create_mlp_project, create_mlp_run
    from mlpcopilot.runtime.workstate import apply_project_command
    from mlpcopilot.session.manager import SessionManager

    create_mlp_project(tmp_path, name="A", project_id="proj_a")
    create_mlp_run(tmp_path, "proj_a", run_id="run_a")
    create_mlp_project(tmp_path, name="B", project_id="proj_b")
    create_mlp_run(tmp_path, "proj_b", run_id="run_b")
    _write_display_doc(tmp_path, "proj_a", "run_a", "project-a")
    _write_display_doc(tmp_path, "proj_b", "run_b", "project-b")
    sessions = SessionManager(tmp_path)
    session = sessions.get_or_create("tui:default")
    apply_project_command(session, "set proj_a run_a", workspace=tmp_path)
    sessions.save(session)
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )

    session_data = collect_tui_render_data(config, session_id="tui:default")
    workspace_data = collect_tui_render_data(config)

    assert session_data.companion_display is not None
    assert session_data.companion_display["summary"] == "project-a"
    assert workspace_data.companion_display is not None
    assert workspace_data.companion_display["summary"] == "project-b"


def test_training_controller_syncs_generated_config_into_project_run_schema(tmp_path) -> None:
    import sys
    from pathlib import Path

    from mlpcopilot.runtime.workspace import create_mlp_project, create_mlp_run

    mcp_src = Path(__file__).parents[2] / "mlpcopilot" / "mcps" / "mlp_training_controller_mcp" / "src"
    sys.path.insert(0, str(mcp_src))
    from mlp_training_controller_mcp.backends.dpgen_common import _sync_project_run_config

    create_mlp_project(tmp_path, name="FeCH", project_id="proj_sync")
    create_mlp_run(tmp_path, "proj_sync", run_id="run_sync")
    run_dir = tmp_path / "projects" / "proj_sync" / "runs" / "run_sync"
    output = run_dir / "controller" / "generated_param.json"
    output.write_text('{"type_map": ["Fe"]}\n', encoding="utf-8")
    artifacts: list[dict] = []
    warnings: list[str] = []

    _sync_project_run_config(output, "param.json", artifacts, warnings)

    assert warnings == []
    assert (run_dir / "controller" / "rendered_inputs" / "param.json").read_text(encoding="utf-8") == output.read_text(
        encoding="utf-8"
    )
    assert (run_dir / "backend" / "dpgen" / "param.json").read_text(encoding="utf-8") == output.read_text(
        encoding="utf-8"
    )
    assert len(artifacts) == 2


def _write_display_doc(tmp_path, project_id: str, run_id: str, summary: str) -> None:
    display = {
        "kind": "display_document",
        "title": "DP-GEN Companion",
        "summary": summary,
        "body": [{"type": "key_values", "items": [{"key": "Run", "value": run_id}]}],
    }
    path = tmp_path / "projects" / project_id / "runs" / run_id / "ui" / "companion.display.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(display), encoding="utf-8")
