from .common import *  # noqa: F403


def test_tui_tool_arg_formatting_prefers_single_line_summaries() -> None:
    assert _format_args({"command": "rm /tmp/demo"}) == "rm /tmp/demo"
    assert _format_args({"path": "/tmp/demo.txt"}) == "/tmp/demo.txt"
    assert _format_args({"action": "check", "key": "exec_config"}) == "check exec_config"

def test_tui_campaign_pane_reads_adapter_display_document(tmp_path) -> None:
    display = {
        "kind": "display_document",
        "body": [
            {
                "type": "key_values",
                "items": [
                    {"key": "campaign", "value": "al_001"},
                    {"key": "state", "value": "dft_running"},
                    {"key": "iteration", "value": "2"},
                ],
            }
        ],
    }

    console = Console(record=True, width=70)
    console.print(_campaign_renderable(tmp_path, companion_display=display))
    output = console.export_text(styles=False)

    assert "campaign" in output
    assert "al_001" in output
    assert "dft_running" in output

def test_tui_campaign_pane_uses_workstate_without_adapter_display(tmp_path) -> None:
    summary = "goal: custom_001\nplan: queued"

    console = Console(record=True, width=70)
    console.print(_campaign_renderable(tmp_path, workstate_display=summary))
    output = console.export_text(styles=False)

    assert "custom_001" in output
    assert "queued" in output

def test_tui_tool_log_uses_single_line_entries() -> None:
    state = RuntimeTuiState()
    state.record_tool_events([
        {
            "name": "exec",
            "phase": "error",
            "arguments": {"command": "rm 1.sh"},
            "error": "Error: Approval required before executing command.",
        }
    ])

    console = Console(record=True, width=70)
    console.print(_tool_log_renderable(state, [], [{} for _ in range(9)]))
    output = console.export_text(styles=False)

    assert _tool_log_panel_title([], [{} for _ in range(9)]) == "Tool Log | mcp(0) skills(9)"
    assert "mcp (0)" not in output
    assert "Datetime" in output
    assert "State" in output
    assert "Tools" in output
    assert "Action" in output
    assert "Time" in output
    assert "Pending" in output
    assert "exec" in output
    assert '"rm 1.sh"' in output
    assert ' "rm 1.sh"                   -' in output
    assert "Approval required before executing command" not in output
    assert "e…" not in output
    assert "m…" not in output

def test_tui_tool_log_action_column_expands_with_viewport_width() -> None:
    state = RuntimeTuiState()
    state.tool_log.append(
        ToolLogEntry(
            name="mcp",
            status="ok",
            detail="task=abcdefghijklmnopqrstuvwxyz0123456789",
            duration_s=0.01,
        )
    )

    narrow_console = Console(record=True, width=70)
    narrow_console.print(_tool_log_renderable(state, [], []))
    narrow = narrow_console.export_text(styles=False)
    wide_console = Console(record=True, width=120)
    wide_console.print(_tool_log_renderable(state, [], [], viewport_width=100))
    wide = wide_console.export_text(styles=False)

    assert "task=abcdefghijklmno..." in narrow
    assert "task=abcdefghijklmnopqrstuvwxyz0123456789" in wide

def test_tui_tool_log_empty_state_has_no_idle_row() -> None:
    console = Console(record=True, width=70)
    console.print(_tool_log_renderable(RuntimeTuiState(), [], []))
    output = console.export_text(styles=False)

    assert "mcp (0)" not in output
    assert "idle (none)" not in output
    assert "No tool calls" not in output


def test_tui_tool_log_empty_state_shows_mcp_failure_reason() -> None:
    state = RuntimeTuiState()
    mcp_servers = [{"name": "remote", "type": "streamableHttp"}]
    mcp_status = {
        "connected": [],
        "errors": [
            {
                "server": "remote",
                "message": "remote: streamableHttp connection failed: http://mcp.example.test/mcp",
            }
        ],
    }

    console = Console(record=True, width=120)
    console.print(_tool_log_renderable(state, mcp_servers, [], mcp_status=mcp_status))
    output = console.export_text(styles=False)

    assert "failed remote streamableHttp" in output
    assert "streamableHttp connection failed" in output


def test_tui_tool_log_marks_background_exec() -> None:
    state = RuntimeTuiState()
    state.record_tool_events(
        [
            {
                "name": "exec",
                "phase": "start",
                "call_id": "call-bg",
                "arguments": {"command": "cmatrix"},
            },
            {
                "name": "exec",
                "phase": "end",
                "call_id": "call-bg",
                "arguments": {"command": "cmatrix"},
                "result": "Background exec started.\nPID: 123",
            },
        ]
    )

    console = Console(record=True, width=70)
    console.print(_tool_log_renderable(state, [], []))
    output = console.export_text(styles=False)

    assert "BG" in output
    assert '"cmatrix"' in output

def test_tui_tool_log_persists_and_reloads(tmp_path) -> None:
    entries = [
        ToolLogEntry(
            name="exec",
            status="background",
            detail="cmatrix",
            duration_s=0.01,
            raw_path="logs/raw-tool-results/call_exec.txt",
        ),
        ToolLogEntry(name="grep", status="ok", detail="pattern=x", duration_s=0.02),
    ]

    save_persisted_tool_log(tmp_path, entries)
    loaded = load_persisted_tool_log(tmp_path)

    assert [(entry.name, entry.status, entry.detail) for entry in loaded] == [
        ("exec", "background", "cmatrix"),
        ("grep", "ok", "pattern=x"),
    ]
    assert loaded[0].raw_path == "logs/raw-tool-results/call_exec.txt"
    assert (tmp_path / "logs" / "tool-log.jsonl").exists()

def test_tui_tool_log_session_save_mirrors_global_log(tmp_path) -> None:
    entries = [
        ToolLogEntry(name="exec", status="ok", detail="session-a", duration_s=0.01),
    ]

    save_persisted_tool_log(tmp_path, entries, session_id="tui:session-a")

    assert (tmp_path / "logs" / "sessions" / "tui_session-a.tool-log.jsonl").exists()
    assert (tmp_path / "logs" / "tool-log.jsonl").exists()
    assert [(entry.name, entry.status, entry.detail) for entry in load_persisted_tool_log(tmp_path)] == [
        ("exec", "ok", "session-a"),
    ]

def test_tui_tool_log_session_load_falls_back_to_global_log(tmp_path) -> None:
    save_persisted_tool_log(
        tmp_path,
        [ToolLogEntry(name="grep", status="ok", detail="pattern=force")],
    )

    loaded = load_persisted_tool_log(tmp_path, session_id="tui:missing")

    assert [(entry.name, entry.status, entry.detail) for entry in loaded] == [
        ("grep", "ok", "pattern=force"),
    ]

def test_tui_tool_log_session_load_can_disable_global_fallback(tmp_path) -> None:
    save_persisted_tool_log(
        tmp_path,
        [ToolLogEntry(name="grep", status="ok", detail="pattern=force")],
    )

    loaded = load_persisted_tool_log(
        tmp_path,
        session_id="tui:missing",
        fallback_to_global=False,
    )

    assert loaded == []

def test_tui_tool_log_global_log_merges_sessions(tmp_path) -> None:
    save_persisted_tool_log(
        tmp_path,
        [ToolLogEntry(name="exec", status="ok", detail="session-a")],
        session_id="tui:session-a",
    )
    save_persisted_tool_log(
        tmp_path,
        [ToolLogEntry(name="mcp_tool", status="ok", detail="session-b")],
        session_id="tui:session-b",
    )

    loaded = load_persisted_tool_log(tmp_path)

    assert [(entry.name, entry.status, entry.detail) for entry in loaded] == [
        ("exec", "ok", "session-a"),
        ("mcp_tool", "ok", "session-b"),
    ]

async def test_tui_progress_persists_mcp_raw_result(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    state = RuntimeTuiState()
    controller = TuiRuntimeController(
        config=config,
        state=state,
        agent_loop=_FakeLoop(tmp_path),
        session_id="tui:default",
        queue=asyncio.Queue(),
        app_ref={},
    )

    await controller.progress(
        "",
        tool_events=[
            {
                "name": "mcp_agentic_search",
                "phase": "start",
                "call_id": "call_raw",
                "arguments": {"task": "inspect db"},
            },
            {
                "name": "mcp_agentic_search",
                "phase": "end",
                "call_id": "call_raw",
                "arguments": {"task": "inspect db"},
                "result": '{"answer": "ok", "raw": [1, 2, 3]}',
            },
        ],
    )

    assert len(state.tool_log) == 1
    assert state.tool_log[0].raw_path.startswith("logs/raw-tool-results/")
    raw_path = tmp_path / state.tool_log[0].raw_path
    assert raw_path.read_text(encoding="utf-8") == '{"answer": "ok", "raw": [1, 2, 3]}'
    assert load_persisted_tool_log(tmp_path, session_id=state.active_session_id)[0].raw_path == state.tool_log[0].raw_path
    jobs = JobStore(tmp_path).list_jobs(limit=None)
    assert len(jobs) == 1
    assert jobs[0].kind == "mcp"
    assert jobs[0].status == "exited"
    assert jobs[0].log_path == state.tool_log[0].raw_path
    assert "mcp_agentic_search" in jobs[0].command

def test_tui_tool_log_reload_defaults_to_extended_recent_history(tmp_path) -> None:
    entries = [
        ToolLogEntry(name="exec", status="ok", detail=f"command-{idx}")
        for idx in range(205)
    ]

    save_persisted_tool_log(tmp_path, entries, limit=205)
    loaded = load_persisted_tool_log(tmp_path)

    assert len(loaded) == 200
    assert loaded[0].detail == "command-5"
    assert loaded[-1].detail == "command-204"

def test_tui_tool_log_viewport_keeps_newest_visible_entries() -> None:
    state = RuntimeTuiState()
    for idx in range(6):
        state.record_tool_events(
            [
                {
                    "name": "exec",
                    "phase": "start",
                    "call_id": f"call-{idx}",
                    "arguments": {"command": f"command-{idx}"},
                },
                {
                    "name": "exec",
                    "phase": "end",
                    "call_id": f"call-{idx}",
                    "arguments": {"command": f"command-{idx}"},
                },
            ]
        )

    console = Console(record=True, width=90)
    console.print(_tool_log_renderable(state, [], [], viewport_height=4))
    output = console.export_text(styles=False)

    assert "Datetime" in output
    assert "command-0" not in output
    assert "command-1" not in output
    assert "command-2" not in output
    assert "command-3" in output
    assert "command-4" in output
    assert "command-5" in output

def test_tui_tool_log_keeps_extended_history_for_pager() -> None:
    state = RuntimeTuiState()
    for idx in range(205):
        state.record_tool_events(
            [
                {
                    "name": "exec",
                    "phase": "end",
                    "call_id": f"call-{idx}",
                    "arguments": {"command": f"command-{idx}"},
                }
            ]
        )

    assert len(state.tool_log) == 200
    assert state.tool_log[0].detail == "command-5"
    assert state.tool_log[-1].detail == "command-204"

def test_tui_tool_log_pager_renders_scrollable_entries() -> None:
    state = RuntimeTuiState(tool_log_pager_scroll=99)
    for idx in range(6):
        state.tool_log.append(
            ToolLogEntry(
                name="exec",
                status="ok",
                detail=f"command-{idx}",
                duration_s=0.01,
            )
        )

    output = _render_tool_log_pager_ansi(state, width=90, height=7)

    assert "tool log 6 entries" in output
    assert "PgUp/PgDn scroll" in output
    assert "Datetime" in output
    assert '"command-0"' not in output
    assert '"command-5"' in output
    assert state.tool_log_pager_scroll == 3

def test_tui_tool_log_pager_renders_empty_state() -> None:
    output = _render_tool_log_pager_ansi(RuntimeTuiState(), width=80, height=8)

    assert "No tool log entries are available." in output
    assert "Esc closes this pager." in output
