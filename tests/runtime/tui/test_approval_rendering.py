from mlpcopilot.runtime.tui.commands.command_approvals import (
    _handle_tui_approval_command,
    _limit_tui_resume_output,
)
from mlpcopilot.runtime.tui.overlays.approvals import _approvals_renderable

from .common import *  # noqa: F403


class _SlowApprovalExecTool:
    parameters = {"properties": {"approval_id": {"type": "string"}}}

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def execute(self, **kwargs):
        self.started.set()
        await self.release.wait()
        return "Exit code: 0"


def test_tui_approval_focus_shows_structured_decision_context(tmp_path) -> None:
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
        metadata={
            "tool": "exec",
            "command": "rm 1.txt",
            "working_dir": str(tmp_path),
        },
    )

    console = Console(record=True, width=180)
    console.print(render_tui(config, RuntimeTuiState()))
    output = console.export_text(styles=False)

    assert "Approval Required" in output
    assert approval.approval_id in output
    assert "Action:" in output
    assert "Exec Command" in output
    assert "Target:" in output
    assert "rm 1.txt" in output
    assert "[high]" in output
    assert "> Approve" in output
    assert "Esc/Ctrl-N/F3" in output

def test_tui_approval_selection_wraps_and_renders_current_choice(tmp_path) -> None:
    sync_mlpcopilot_workspace(tmp_path, silent=True)
    approval = ApprovalManager(tmp_path).create(
        action_type="exec_command",
        title="Approve exec",
        request="Run command",
        metadata={"tool": "exec", "command": "rm 1.txt"},
    )

    rendered = _approval_focus_renderable(approval, selection=1).plain

    assert _selected_approval_action(0) == "approve"
    assert _selected_approval_action(1) == "reject"
    assert _selected_approval_action(2) == "changes"
    assert _selected_approval_action(-1) == "changes"
    assert "> Reject" in rendered
    assert "  Approve" in rendered
    assert "  Request changes" in rendered

def test_tui_approvals_pane_only_shows_pending(tmp_path) -> None:
    sync_mlpcopilot_workspace(tmp_path, silent=True)
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path), "model": "test/model"}},
        }
    )
    manager = ApprovalManager(tmp_path)
    pending = manager.create(
        action_type="exec_command",
        title="Pending command",
        request="Run command",
    )
    approved = manager.create(
        action_type="exec_command",
        title="Approved command",
        request="Run old command",
    )
    manager.approve(approved.approval_id, decided_by="test")

    console = Console(record=True, width=180)
    console.print(render_tui(config, RuntimeTuiState()))
    output = console.export_text(styles=False)

    assert pending.approval_id in output
    assert approved.approval_id not in output
    assert "Approved command" not in output
    assert "Approvals (1)" in output

def test_tui_approvals_pane_shows_recent_decisions_when_no_pending(tmp_path) -> None:
    sync_mlpcopilot_workspace(tmp_path, silent=True)
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path), "model": "test/model"}},
        }
    )
    manager = ApprovalManager(tmp_path)
    approval = manager.create(
        action_type="exec_command",
        title="Approved command",
        request="Run old command",
        metadata={"tool": "exec", "command": "cmatrix"},
    )
    manager.approve(approval.approval_id, decided_by="test")

    console = Console(record=True, width=180)
    console.print(render_tui(config, RuntimeTuiState()))
    output = console.export_text(styles=False)

    assert "Approvals (0)" in output
    assert approval.approval_id in output
    assert "approved" in output
    assert "cmatrix" in output

async def test_tui_approval_resume_records_running_tool_log(tmp_path) -> None:
    sync_mlpcopilot_workspace(tmp_path, silent=True)
    manager = ApprovalManager(tmp_path)
    approval = manager.create(
        action_type="exec_command",
        title="Approve exec",
        request="Run command",
        metadata={
            "tool": "exec",
            "command": "sleep 30",
            "working_dir": str(tmp_path),
        },
    )
    state = RuntimeTuiState()
    tool = _SlowApprovalExecTool()
    task = asyncio.create_task(
        _handle_tui_approval_command(
            Config.model_validate(
                {
                    "runtimeProfile": "mlpcopilot",
                    "agents": {"defaults": {"workspace": str(tmp_path)}},
                }
            ),
            _FakeLoop(tmp_path, exec_tool=tool),
            f"/approve {approval.approval_id}",
            state,
        )
    )

    await tool.started.wait()

    assert len(state.tool_log) == 1
    assert state.tool_log[0].status == "running"
    assert state.tool_log[0].detail == "sleep 30"

    tool.release.set()
    result = await task

    assert result is not None
    assert 'exec "sleep 30" completed OK' in result
    assert state.tool_log[0].status == "ok"
    assert state.tool_log[0].duration_s is not None

def test_tui_resume_output_sanitizes_terminal_controls_before_truncating() -> None:
    raw = (
        "\x1b[?25l\x1b[?7llogo\n"
        "\x1b[20A\x1b[9999999D\x1b[43C\x1b[31mCPU\x1b[0m: AMD "
        + ("x" * 200)
    )

    limited = _limit_tui_resume_output(raw, limit=100)

    assert "\x1b[?25l" not in limited
    assert "\x1b[20A" not in limited
    assert "\x1b[43C" not in limited
    assert "CPU" in limited
    assert "output truncated" in limited

def test_tui_approvals_rows_stay_single_line_when_narrow(tmp_path) -> None:
    approval = ApprovalManager(tmp_path).create(
        action_type="exec_command",
        title="Approved command",
        request="Run old command",
        metadata={
            "tool": "exec",
            "command": "which cmatrix 2>/dev/null || echo 'not found'",
        },
    )
    manager = ApprovalManager(tmp_path)
    manager.approve(approval.approval_id, decided_by="test")

    console = Console(record=True, width=64)
    console.print(_approvals_renderable([], manager.list_decisions(), viewport_width=60))
    lines = [line.rstrip() for line in console.export_text(styles=False).splitlines() if line.strip()]

    assert len(lines) == 1
    assert approval.approval_id in lines[0]
    assert "approved" in lines[0]
    assert "which c" in lines[0]

def test_tui_log_entries_render_inside_tool_log(tmp_path) -> None:
    sync_mlpcopilot_workspace(tmp_path, silent=True)
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path), "model": "test/model"}},
        }
    )
    state = RuntimeTuiState()
    state.record_log(
        "ERROR",
        "mlpcopilot.agent.tools.mcp",
        "MCP server 'LabGateway': failed to connect",
    )

    console = Console(record=True, width=180)
    console.print(render_tui(config, state))
    output = console.export_text(styles=False)

    assert "Error" in output
    assert "mcp" in output
    assert "LabGateway" in output

def test_tui_captures_runtime_warnings_without_debug_noise() -> None:
    from loguru import logger

    state = RuntimeTuiState()

    with capture_tui_logs(state):
        logger.debug("debug should stay hidden")
        logger.warning("No MCP servers connected successfully (will retry next message)")

    assert len(state.tool_log) == 1
    assert state.tool_log[0].name == "agent"
    assert state.tool_log[0].detail == "No MCP servers connected; retrying"

def test_tui_artifacts_do_not_scan_recent_workspace_files(tmp_path) -> None:
    sync_mlpcopilot_workspace(tmp_path, silent=True)
    (tmp_path / "to.txt").write_text("", encoding="utf-8")
    (tmp_path / "sessions").mkdir(exist_ok=True)
    (tmp_path / "sessions" / "tui.jsonl").write_text("{}", encoding="utf-8")
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path), "model": "test/model"}},
        }
    )

    console = Console(record=True, width=180)
    console.print(render_tui(config, RuntimeTuiState()))
    output = console.export_text(styles=False)

    assert "(no adapter display)" in output
    assert "to.txt" not in output
    assert "sessions/tui.jsonl" not in output
