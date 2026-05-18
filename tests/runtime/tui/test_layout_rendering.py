import json

from rich.panel import Panel

from mlpcopilot.runtime.workspace import create_mlp_project, create_mlp_run
from mlpcopilot.runtime.workstate import apply_goal_command, apply_plan_command

from .common import *  # noqa: F403


def _write_companion_display(tmp_path, project_id: str, run_id: str, items: list[dict[str, str]]) -> None:
    display_path = tmp_path / "projects" / project_id / "runs" / run_id / "ui" / "companion.display.json"
    display_path.parent.mkdir(parents=True, exist_ok=True)
    display_path.write_text(_companion_display_json(items), encoding="utf-8")


def _companion_display_json(items: list[dict[str, str]]) -> str:
    return json.dumps(
        {
            "kind": "display_document",
            "body": [
                {
                    "type": "key_values",
                    "items": items,
                }
            ],
        }
    )


def test_render_tui_shows_runtime_panes_and_state(tmp_path) -> None:
    sync_mlpcopilot_workspace(tmp_path, silent=True)
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path), "model": "test/model"}},
        }
    )
    state = RuntimeTuiState()
    approval = ApprovalManager(tmp_path, session_key=state.active_session_id).create(
        action_type="costly_job",
        title="Run validation",
        request="Launch validation",
    )
    ArtifactIndex(tmp_path).create_run(
        run_id="run_tui",
        source="mcp:test:tool",
        artifacts=["runs/run_tui/result.json"],
    )
    state.add_chat("user", "validate dataset")
    state.mcp_status = {"state": "disconnected", "connected_count": 0, "configured_count": 0}

    console = Console(record=True, width=180)
    console.print(render_tui(config, state))
    output = console.export_text(styles=False)

    assert "Chat / Task" in output
    assert "current model: test/model" in output
    assert "Tool Log" in output
    assert "Companion" in output
    assert "mcp(0)" in output
    assert "skills(" in output
    assert "Artifacts" in output
    assert "(no adapter display)" in output
    assert "Approvals (1)" in output
    assert approval.approval_id in output
    assert "Approval Required" in output
    assert "Enter/Ctrl-Y/F2 approve" in output
    assert "pending approvals" not in output

def test_render_tui_body_dispatches_to_four_pane_layout(tmp_path) -> None:
    sync_mlpcopilot_workspace(tmp_path, silent=True)
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path), "model": "test/model"}},
        }
    )
    state = RuntimeTuiState()

    body = render_tui_body(config, state)
    four_pane = render_four_pane_body(config, state)

    console = Console(record=True, width=160)
    console.print(body)
    body_output = console.export_text(styles=False)
    console = Console(record=True, width=160)
    console.print(four_pane)
    four_pane_output = console.export_text(styles=False)

    assert "Chat / Task" in body_output
    assert "Companion" in body_output
    assert body_output == four_pane_output

def test_render_compact_body_shows_compact_runtime_panes(tmp_path) -> None:
    sync_mlpcopilot_workspace(tmp_path, silent=True)
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path), "model": "test/model"}},
        }
    )
    state = RuntimeTuiState(layout_name="compact")
    state.add_chat("assistant", "compact ready")

    console = Console(record=True, width=120)
    console.print(render_compact_body(config, state))
    output = console.export_text(styles=False)

    assert "Chat / Task" in output
    assert "Tool Log" in output
    assert "Artifacts" in output
    assert "(no adapter display)" in output
    assert "Approvals" in output
    assert "Companion" not in output

def test_render_campaign_focus_body_shows_companion_display(tmp_path) -> None:
    sync_mlpcopilot_workspace(tmp_path, silent=True)
    project = create_mlp_project(tmp_path, name="demo", project_id="proj_campaign")
    run = create_mlp_run(tmp_path, project["project_id"], run_id="run_campaign")
    _write_companion_display(
        tmp_path,
        project["project_id"],
        run["run_id"],
        [
            {"key": "campaign", "value": "al_002"},
            {"key": "state", "value": "sampling"},
            {"key": "iteration", "value": "3"},
        ],
    )
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path), "model": "test/model"}},
        }
    )
    state = RuntimeTuiState(layout_name="campaign_focus")
    state.add_chat("assistant", "campaign ready")

    console = Console(record=True, width=180)
    console.print(render_campaign_focus_body(config, state))
    output = console.export_text(styles=False)

    assert "Chat / Task" in output
    assert "Tool Log" in output
    assert "Companion" in output
    assert "al_002" in output
    assert "Artifacts" in output
    assert "Approvals" in output

def test_render_campaign_focus_body_loads_campaign_status_json(tmp_path) -> None:
    sync_mlpcopilot_workspace(tmp_path, silent=True)
    status_path = tmp_path / "campaign" / "status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps(
            {
                "campaign_id": "al_001",
                "state": "training",
                "iteration": 4,
                "dataset": {"path": "datasets/current", "artifact_id": "artifact_dataset"},
                "checkpoint": {"path": "checkpoints/model.pt", "artifact_id": "artifact_ckpt"},
                "jobs": [{"job_id": "job_train", "kind": "train", "status": "running"}],
                "next_decision": {
                    "approval_id": "apr_train",
                    "summary": "Approve next validation batch",
                },
                "blockers": [{"message": "waiting for GPU slot", "status": "queued"}],
                "artifacts": [{"artifact_id": "artifact_report", "type": "report"}],
            }
        ),
        encoding="utf-8",
    )
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path), "model": "test/model"}},
        }
    )
    state = RuntimeTuiState(layout_name="campaign_focus")

    console = Console(record=True, width=180)
    console.print(render_campaign_focus_body(config, state))
    output = console.export_text(styles=False)

    assert "al_001" in output
    assert "training" in output
    assert "4" in output
    assert "datasets/current" in output
    assert "checkpoints/model.pt" in output
    assert "job_train" in output
    assert "Approve next validation batch" in output
    assert "waiting for GPU slot" in output
    assert "artifact_report" in output

def test_render_campaign_focus_body_uses_configured_campaign_status_path(tmp_path) -> None:
    sync_mlpcopilot_workspace(tmp_path, silent=True)
    status_path = tmp_path / "custom" / "status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps({"campaign_id": "custom_campaign", "state": "blocked"}),
        encoding="utf-8",
    )
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path), "model": "test/model"}},
            "tui": {"campaignStatusPaths": ["custom/status.json"]},
        }
    )
    state = RuntimeTuiState(layout_name="campaign_focus")

    console = Console(record=True, width=180)
    console.print(render_campaign_focus_body(config, state))
    output = console.export_text(styles=False)

    assert "custom_campaign" in output
    assert "blocked" in output

def test_render_campaign_focus_body_respects_empty_campaign_status_paths(tmp_path) -> None:
    sync_mlpcopilot_workspace(tmp_path, silent=True)
    status_path = tmp_path / "campaign" / "status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps({"campaign_id": "disabled_campaign", "state": "blocked"}),
        encoding="utf-8",
    )
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path), "model": "test/model"}},
            "tui": {"campaignStatusPaths": []},
        }
    )
    state = RuntimeTuiState(layout_name="campaign_focus")

    console = Console(record=True, width=180)
    console.print(render_campaign_focus_body(config, state))
    output = console.export_text(styles=False)

    assert "disabled_campaign" not in output
    assert "(no adapter display)" in output

def test_render_four_pane_body_shows_session_goal_and_plan(tmp_path) -> None:
    sync_mlpcopilot_workspace(tmp_path, silent=True)
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path), "model": "test/model"}},
        }
    )
    sessions = SessionManager(tmp_path)
    session = sessions.get_or_create("tui:default")
    apply_goal_command(session, "finish DP-GEN iteration")
    apply_plan_command(session, "add inspect dispatcher errors")
    sessions.save(session)
    state = RuntimeTuiState()

    console = Console(record=True, width=180)
    console.print(render_four_pane_body(config, state))
    output = console.export_text(styles=False)

    assert "goal: finish DP-GEN iteration" in output
    assert "inspect dispatcher errors" in output


def test_companion_keeps_goal_plan_summary_with_adapter_display() -> None:
    display = {
        "kind": "display_document",
        "producer": "dpgen_adapter",
        "updated_at": "2026-05-09T00:00:00+00:00",
        "body": [
            {
                "type": "key_values",
                "items": [
                    {"key": "Run", "value": "run_local"},
                    {"key": "State", "value": "iter.000021"},
                ],
            }
        ],
    }
    renderable = _campaign_renderable(
        Path("/tmp"),
        companion_display=display,
        workstate_display="goal: test\nplan: print 123",
    )

    console = Console(record=True, width=80, height=10)
    console.print(Panel(renderable, height=8))
    output = console.export_text(styles=False)

    assert "run_local" in output
    assert "source: dpgen_adapter" in output
    assert "updated: 2026-05-09T00:00:00+00:00" in output
    assert "goal: test" in output
    assert "plan: print 123" in output


def test_companion_prefers_status_source_metadata() -> None:
    display = {
        "kind": "display_document",
        "status_source": "record.dpgen + iteration directories",
        "queried_at": "2026-05-09T01:02:03+00:00",
        "body": [
            {
                "type": "key_values",
                "items": [
                    {"key": "State", "value": "iter.000021 stage0"},
                ],
            }
        ],
    }
    renderable = _campaign_renderable(
        Path("/tmp"),
        companion_display=display,
        workstate_display="goal: -\nplan: -",
    )

    console = Console(record=True, width=120, height=10)
    console.print(Panel(renderable, height=8))
    output = console.export_text(styles=False)

    assert "source: record.dpgen + iteration directories" in output
    assert "updated: 2026-05-09T01:02:03+00:00" in output


def test_companion_marks_stale_display_document() -> None:
    display = {
        "kind": "display_document",
        "producer": "dpgen_adapter",
        "updated_at": "2000-01-01T00:00:00+00:00",
        "body": [
            {
                "type": "key_values",
                "items": [
                    {"key": "State", "value": "iter.000001 stage1"},
                ],
            }
        ],
    }
    renderable = _campaign_renderable(
        Path("/tmp"),
        companion_display=display,
        workstate_display="goal: -\nplan: -",
    )

    console = Console(record=True, width=120, height=10)
    console.print(Panel(renderable, height=8))
    output = console.export_text(styles=False)

    assert "source: dpgen_adapter" in output
    assert "stale:" in output


def test_companion_stale_marker_can_be_disabled() -> None:
    display = {
        "kind": "display_document",
        "producer": "dpgen_adapter",
        "updated_at": "2000-01-01T00:00:00+00:00",
        "body": [
            {
                "type": "key_values",
                "items": [
                    {"key": "State", "value": "iter.000001 stage1"},
                ],
            }
        ],
    }
    renderable = _campaign_renderable(
        Path("/tmp"),
        companion_display=display,
        workstate_display="goal: -\nplan: -",
        stale_after_seconds=0,
    )

    console = Console(record=True, width=120, height=10)
    console.print(Panel(renderable, height=8))
    output = console.export_text(styles=False)

    assert "source: dpgen_adapter" in output
    assert "stale:" not in output


def test_render_campaign_focus_body_uses_adapter_display_document(tmp_path) -> None:
    sync_mlpcopilot_workspace(tmp_path, silent=True)
    project = create_mlp_project(tmp_path, name="demo", project_id="proj_display")
    run = create_mlp_run(tmp_path, project["project_id"], run_id="run_display")
    display_path = (
        tmp_path
        / "projects"
        / project["project_id"]
        / "runs"
        / run["run_id"]
        / "ui"
        / "companion.display.json"
    )
    display_path.parent.mkdir(parents=True, exist_ok=True)
    display_path.write_text(
        _companion_display_json(
            [
                {"key": "Run", "value": "Configured campaign"},
                {"key": "State", "value": "running"},
            ]
        ),
        encoding="utf-8",
    )
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path), "model": "test/model"}},
        }
    )
    state = RuntimeTuiState(layout_name="campaign_focus")

    console = Console(record=True, width=180)
    console.print(render_campaign_focus_body(config, state))
    output = console.export_text(styles=False)

    assert "Configured campaign" in output
    assert "running" in output

def test_render_approval_focus_body_shows_review_workspace(tmp_path) -> None:
    sync_mlpcopilot_workspace(tmp_path, silent=True)
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path), "model": "test/model"}},
        }
    )
    approval = ApprovalManager(tmp_path).create(
        action_type="exec_command",
        title="Approve exec",
        request="Run command",
    )
    state = RuntimeTuiState(layout_name="approval_focus")
    state.add_chat("assistant", "review ready")

    console = Console(record=True, width=160)
    console.print(render_approval_focus_body(config, state))
    output = console.export_text(styles=False)

    assert "Chat / Task" in output
    assert "Tool Log" in output
    assert "Approvals (1)" in output
    assert approval.approval_id in output
    assert "Artifacts" in output

def test_tui_prompt_layout_builds_prompt_toolkit_root(tmp_path) -> None:
    from prompt_toolkit.layout import Layout as PromptLayout
    from prompt_toolkit.widgets import TextArea

    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path), "model": "test/model"}},
        }
    )
    layout = build_tui_prompt_layout(
        config=config,
        state=RuntimeTuiState(),
        input_box=TextArea(height=1),
    )

    assert isinstance(layout, PromptLayout)

def test_tui_workspace_path_display_uses_tilde_for_home() -> None:
    display = _display_workspace_path(Path.home() / ".mlpcopilot" / "workspace")

    assert display == "~/.mlpcopilot/workspace"

def test_tui_footer_shows_short_keys_and_policy(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path), "model": "test/model"}},
            "tools": {
                "approvalRequiredForTools": True,
                "approvalGatedWrites": True,
            },
        }
    )

    footer = _footer_help_line(config, RuntimeTuiState(), []).plain

    assert "Enter send" in footer
    assert "Up/Down history" in footer
    assert "PgUp/PgDn chat" in footer
    assert "Ctrl-T pager" in footer
    assert "Ctrl-L tool log" in footer
    assert "Ctrl-P jobs" in footer
    assert "Ctrl-O layout" in footer
    assert "F6 model" in footer
    assert "idle" in footer
    assert "writes" in footer
    assert "tools" in footer
    assert "gated" in footer
    assert "Ctrl-C/Ctrl-D quit" in footer

def test_tui_footer_uses_configured_short_keys(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path), "model": "test/model"}},
            "tui": {
                "keymap": {
                    "pager": "f7",
                    "toolLog": "f8",
                    "jobs": "f9",
                    "layout": "f10",
                    "quit": "f12",
                }
            },
        }
    )

    footer = _footer_help_line(config, RuntimeTuiState(), []).plain

    assert "F7 pager" in footer
    assert "F8 tool log" in footer
    assert "F9 jobs" in footer
    assert "F10 layout" in footer
    assert "F12 quit" in footer
    assert "Ctrl-T pager" not in footer
    assert "Ctrl-C quit" not in footer

def test_tui_footer_shows_job_picker_keys(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path), "model": "test/model"}},
        }
    )
    state = RuntimeTuiState()
    state.open_overlay("job_picker")

    footer = _footer_help_line(config, state, []).plain

    assert "Up/Down select" in footer
    assert "Enter stop" in footer
    assert "Esc close" in footer

def test_tui_footer_shows_layout_picker_keys(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path), "model": "test/model"}},
        }
    )
    state = RuntimeTuiState()
    state.open_overlay("layout_picker")

    footer = _footer_help_line(config, state, []).plain

    assert "Up/Down select" in footer
    assert "Enter switch" in footer
    assert "Esc close" in footer

def test_tui_footer_shows_model_picker_keys(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path), "model": "test/model"}},
        }
    )
    state = RuntimeTuiState()
    state.open_overlay("model_picker")

    footer = _footer_help_line(config, state, []).plain

    assert "Up/Down select" in footer
    assert "Enter switch" in footer
    assert "Esc close" in footer

def test_tui_resets_visible_session_state_for_new_session() -> None:
    state = RuntimeTuiState(
        chat_scroll=4,
        pager_open=True,
        pager_scroll=3,
        pager_message_index=0,
        tool_log_pager_scroll=2,
        job_picker_selection=1,
        layout_picker_selection=1,
        model_picker_selection=1,
    )
    state.add_chat("user", "old")
    state.record_tool_events([
        {"name": "exec", "phase": "start", "arguments": {"command": "ls"}},
    ])

    _reset_tui_session_view(state)

    assert state.chat == []
    assert state.tool_log == []
    assert state.chat_scroll == 0
    assert state.pager_open is False
    assert state.pager_scroll == 0
    assert state.pager_message_index is None
    assert state.tool_log_pager_scroll == 0
    assert state.job_picker_selection == 0
    assert state.layout_picker_selection == 0
    assert state.model_picker_selection == 0

def test_tui_state_tracks_pager_overlay_with_compat_flag() -> None:
    state = RuntimeTuiState()

    state.open_overlay("pager")

    assert state.overlay_stack == ["pager"]
    assert state.pager_open is True
    assert state.is_overlay_open("pager") is True

    state.close_overlay("pager")

    assert state.overlay_stack == []
    assert state.pager_open is False
    assert state.is_overlay_open("pager") is False

def test_tui_state_tracks_tool_log_pager_overlay() -> None:
    state = RuntimeTuiState()

    state.open_overlay("tool_log_pager")

    assert state.overlay_stack == ["tool_log_pager"]
    assert state.is_overlay_open("tool_log_pager") is True
    assert state.pager_open is False

    state.close_overlay("tool_log_pager")

    assert state.overlay_stack == []
    assert state.is_overlay_open("tool_log_pager") is False

def test_tui_state_tracks_job_picker_overlay() -> None:
    state = RuntimeTuiState()

    state.open_overlay("job_picker")

    assert state.overlay_stack == ["job_picker"]
    assert state.is_overlay_open("job_picker") is True
    assert state.pager_open is False

    state.close_overlay("job_picker")

    assert state.overlay_stack == []
    assert state.is_overlay_open("job_picker") is False

def test_tui_state_tracks_layout_picker_overlay() -> None:
    state = RuntimeTuiState()

    state.open_overlay("layout_picker")

    assert state.overlay_stack == ["layout_picker"]
    assert state.is_overlay_open("layout_picker") is True
    assert state.pager_open is False

    state.close_overlay("layout_picker")

    assert state.overlay_stack == []
    assert state.is_overlay_open("layout_picker") is False

def test_tui_state_tracks_model_picker_overlay() -> None:
    state = RuntimeTuiState()

    state.open_overlay("model_picker")

    assert state.overlay_stack == ["model_picker"]
    assert state.is_overlay_open("model_picker") is True
    assert state.pager_open is False

    state.close_overlay("model_picker")

    assert state.overlay_stack == []
    assert state.is_overlay_open("model_picker") is False

def test_tui_state_store_restores_persisted_layout(tmp_path) -> None:
    saved = RuntimeTuiState(layout_name="campaign_focus")
    save_tui_state(tmp_path, saved)
    loaded = RuntimeTuiState()

    apply_persisted_tui_state(loaded, tmp_path)

    assert loaded.layout_name == "campaign_focus"

def test_tui_state_closes_legacy_pager_flag() -> None:
    state = RuntimeTuiState(pager_open=True)

    assert state.is_overlay_open("pager") is True
    state.close_overlay("pager")

    assert state.pager_open is False

def test_tui_fullscreen_env_override(monkeypatch) -> None:
    monkeypatch.delenv("MLPCOPILOT_TUI_FULLSCREEN", raising=False)
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    assert _tui_full_screen_enabled() is True

    monkeypatch.setenv("TERM_PROGRAM", "vscode")
    assert _is_vscode_terminal() is True
    assert _tui_full_screen_enabled() is False

    monkeypatch.setenv("MLPCOPILOT_TUI_FULLSCREEN", "0")
    assert _tui_full_screen_enabled() is False

    monkeypatch.setenv("MLPCOPILOT_TUI_FULLSCREEN", "1")
    assert _tui_full_screen_enabled() is True

def test_tui_layout_style_dict_defines_input_frame_styles() -> None:
    style = tui_style_dict()

    assert style["input-frame"] == "fg:#38bdf8"
    assert "input-frame.border" in style
    assert "input-frame.label" in style
