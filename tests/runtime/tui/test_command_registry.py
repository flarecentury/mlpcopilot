from .common import *  # noqa: F403


def test_tui_command_registry_declares_dispatch_boundaries() -> None:
    runs = get_tui_command("/runs")
    ps = get_tui_command("/ps")
    raw = get_tui_command("/raw")
    tool_log = get_tui_command("/tool-log")
    history = get_tui_command("/history")
    plan = get_tui_command("/plan")
    goal = get_tui_command("/goal")
    project = get_tui_command("/project")
    memory_audit = get_tui_command("/memory_audit")
    new = get_tui_command("/new")
    model = get_tui_command("/model")
    layout = get_tui_command("/layout")

    assert runs is not None
    assert runs.dispatch == "local"
    assert runs.available_during_task is True
    assert ps is not None
    assert ps.name == "/jobs"
    assert ps.dispatch == "local"
    assert ps.available_during_task is True
    assert raw is not None
    assert raw.dispatch == "local"
    assert raw.supports_inline_args is True
    assert tool_log is not None
    assert tool_log.dispatch == "local"
    assert tool_log.available_during_task is True
    assert history is not None
    assert history.dispatch == "local"
    assert history.available_during_task is True
    assert plan is not None
    assert plan.dispatch == "local"
    assert plan.supports_inline_args is True
    assert plan.available_during_task is False
    assert goal is not None
    assert goal.dispatch == "local"
    assert goal.supports_inline_args is True
    assert goal.available_during_task is False
    assert project is not None
    assert project.dispatch == "local"
    assert project.supports_inline_args is True
    assert project.available_during_task is False
    assert memory_audit is not None
    assert memory_audit.name == "/memory-audit"
    assert memory_audit.dispatch == "local"
    assert memory_audit.available_during_task is True
    assert new is not None
    assert new.dispatch == "session"
    assert new.available_during_task is False
    assert model is not None
    assert model.dispatch == "local"
    assert model.available_during_task is False
    assert layout is not None
    assert layout.dispatch == "local"
    assert "/runs" in format_tui_help()
    assert "/dream" in format_tui_help()
    assert "/model" in format_tui_help()
    assert "/memory-audit" in format_tui_help()

def test_tui_command_registry_declares_immediate_commands() -> None:
    assert is_immediate_local_tui_command("/status")
    assert is_immediate_local_tui_command("/history 5")
    assert is_immediate_local_tui_command("/model openai-codex/gpt-5.3-codex")
    assert not is_immediate_local_tui_command("/goal finish the task")
    assert not is_immediate_local_tui_command("/plan add inspect logs")
    assert not is_immediate_local_tui_command("/project set local_dpgen run_local")
    assert is_immediate_local_tui_command("/memory-audit")
    assert is_immediate_local_tui_command("memory_audit")
    assert is_immediate_local_tui_command("toollog")
    assert is_immediate_local_tui_command("/jobs")
    assert is_immediate_local_tui_command("/ps")
    assert is_immediate_local_tui_command("/raw")
    assert is_tui_approval_decision_command("/approve apr_123456789abc")
    assert not is_tui_approval_decision_command("/runs")

def test_tui_command_visibility_can_hide_commands(tmp_path) -> None:
    config = Config.model_validate(
        {
            "commands": {
                "tui": {
                    "hide": ["/dream", "/dream-log", "/dream-restore", "/model"],
                }
            },
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )

    assert "/dream" not in format_tui_help(config)
    assert "/model" not in format_tui_help(config)

def test_tui_completer_suggests_slash_commands_and_models(tmp_path) -> None:
    from prompt_toolkit.completion import CompleteEvent
    from prompt_toolkit.document import Document

    config = Config.model_validate(
        {
            "agents": {
                "defaults": {
                    "workspace": str(tmp_path),
                    "model": "openai-codex/gpt-5.4-mini",
                }
            },
        }
    )
    completer = _make_tui_completer(config)

    slash = list(
        completer.get_completions(
            Document("/app", cursor_position=4),
            CompleteEvent(completion_requested=True),
        )
    )
    models = list(
        completer.get_completions(
            Document("/model openai-codex/gpt-5.", cursor_position=26),
            CompleteEvent(completion_requested=True),
        )
    )
    layouts = list(
        completer.get_completions(
            Document("/layout f", cursor_position=9),
            CompleteEvent(completion_requested=True),
        )
    )

    assert slash[0].text == "/approve "
    assert any(item.text == "openai-codex/gpt-5.3-codex" for item in models)
    assert [item.text for item in layouts] == ["four_pane"]
    compact_layouts = list(
        completer.get_completions(
            Document("/layout c", cursor_position=9),
            CompleteEvent(completion_requested=True),
        )
    )
    assert [item.text for item in compact_layouts] == ["compact", "campaign_focus"]
    approval_layouts = list(
        completer.get_completions(
            Document("/layout a", cursor_position=9),
            CompleteEvent(completion_requested=True),
        )
    )
    assert [item.text for item in approval_layouts] == ["approval_focus"]

def test_tui_completer_suggests_pending_approval_ids(tmp_path) -> None:
    from prompt_toolkit.completion import CompleteEvent
    from prompt_toolkit.document import Document

    sync_mlpcopilot_workspace(tmp_path, silent=True)
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    approval = ApprovalManager(tmp_path).create(
        action_type="tool_execution",
        title="Approve MCP",
        request="Call MCP",
        metadata={"tool": "mcp_dataset_validate", "arguments": {"dataset_path": "/data/v1"}},
    )
    completer = _make_tui_completer(config)

    completions = list(
        completer.get_completions(
            Document("/approve apr_", cursor_position=13),
            CompleteEvent(completion_requested=True),
        )
    )

    assert [item.text for item in completions] == [approval.approval_id]
    assert "MCP Tool Call" in str(completions[0].display_meta_text)

def test_tui_blocks_task_sensitive_slash_commands_while_running() -> None:
    state = RuntimeTuiState(running=True)

    assert _task_running_block_message(state, "/model openai-codex/gpt-5.3-codex") == (
        "/model is disabled while a task is running."
    )
    assert _task_running_block_message(state, "/plan revise validation steps") == (
        "/plan is disabled while a task is running."
    )
    assert _task_running_block_message(state, "/new") == (
        "/new is disabled while a task is running."
    )
    assert _task_running_block_message(state, "/status") is None
    assert _task_running_block_message(state, "/stop") is None
    assert _task_running_block_message(state, "ordinary chat") is None

def test_tui_stop_command_accepts_plain_alias() -> None:
    assert _is_tui_stop_command("/stop")
    assert _is_tui_stop_command("stop")
    assert not _is_tui_stop_command("/status")
