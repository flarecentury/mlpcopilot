"""Tests for exec tool internal URL blocking."""

from __future__ import annotations

import socket
import asyncio
import os
import re
import shlex
import signal
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from mlpcopilot.agent.tools.shell import ExecTool
from mlpcopilot.runtime.approval import ApprovalManager
from mlpcopilot.runtime.jobs import JobStore


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _fake_resolve_private(hostname, port, family=0, type_=0):
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("169.254.169.254", 0))]


def _fake_resolve_localhost(hostname, port, family=0, type_=0):
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 0))]


def _fake_resolve_public(hostname, port, family=0, type_=0):
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))]


@pytest.mark.asyncio
async def test_exec_blocks_curl_metadata():
    tool = ExecTool()
    with patch("mlpcopilot.security.network.socket.getaddrinfo", _fake_resolve_private):
        result = await tool.execute(
            command='curl -s -H "Metadata-Flavor: Google" http://169.254.169.254/computeMetadata/v1/'
        )
    assert "Error" in result
    assert "internal" in result.lower() or "private" in result.lower()


@pytest.mark.asyncio
async def test_exec_blocks_wget_localhost():
    tool = ExecTool()
    with patch("mlpcopilot.security.network.socket.getaddrinfo", _fake_resolve_localhost):
        result = await tool.execute(command="wget http://localhost:8080/secret -O /tmp/out")
    assert "Error" in result


@pytest.mark.asyncio
async def test_exec_allows_normal_commands():
    tool = ExecTool(timeout=5)
    result = await tool.execute(command="echo hello")
    assert "hello" in result
    assert "Error" not in result.split("\n")[0]


@pytest.mark.skipif(sys.platform == "win32", reason="process-group cancellation is POSIX-specific")
@pytest.mark.asyncio
async def test_exec_timeout_kills_child_process_group(tmp_path):
    pidfile = tmp_path / "child.pid"
    tool = ExecTool(timeout=1, working_dir=str(tmp_path))

    result = await tool.execute(
        command=f"sleep 30 & echo $! > {shlex.quote(str(pidfile))}; wait"
    )

    assert "timed out" in result
    child_pid = int(pidfile.read_text(encoding="utf-8").strip())
    for _ in range(20):
        if not _pid_exists(child_pid):
            break
        await asyncio.sleep(0.1)
    assert not _pid_exists(child_pid)


@pytest.mark.skipif(sys.platform == "win32", reason="background exec is POSIX-specific")
@pytest.mark.asyncio
async def test_exec_background_returns_immediately_and_writes_log(tmp_path):
    tool = ExecTool(timeout=1, working_dir=str(tmp_path))

    result = await tool.execute(command="echo ready; sleep 30", background=True)

    assert "Background exec started." in result
    assert "Job:" in result
    assert "PID:" in result
    log_line = next(line for line in result.splitlines() if line.startswith("Log: "))
    job_line = next(line for line in result.splitlines() if line.startswith("Job: "))
    pid_line = next(line for line in result.splitlines() if line.startswith("PID: "))
    job_id = job_line.split(":", 1)[1].strip()
    pid = int(pid_line.split(":", 1)[1].strip())
    log_path = Path(log_line.split(":", 1)[1].strip())
    assert log_path.exists()
    job = JobStore(tmp_path).get(job_id)
    assert job is not None
    assert job.status == "running"
    assert job.pid == pid
    assert job.log_path == f"jobs/{job_id}.log"
    for _ in range(20):
        if "ready" in log_path.read_text(encoding="utf-8", errors="replace"):
            break
        await asyncio.sleep(0.1)
    os.killpg(pid, signal.SIGTERM)
    for _ in range(20):
        if not _pid_exists(pid):
            break
        await asyncio.sleep(0.1)
    assert "ready" in log_path.read_text(encoding="utf-8", errors="replace")


@pytest.mark.asyncio
async def test_exec_large_foreground_output_is_saved_as_finished_job(tmp_path):
    script_file = tmp_path / "gen_output.py"
    script_file.write_text("print('A' * 6000 + chr(10) + 'B' * 6000)", encoding="utf-8")
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(script_file))}"
    tool = ExecTool(timeout=5, working_dir=str(tmp_path))

    result = await tool.execute(command=command)

    assert "Output exceeded" in result
    assert "chars truncated" in result
    match = re.search(r"Full output: (jobs/[^\s]+)", result)
    assert match is not None
    log_path = tmp_path / match.group(1)
    full_output = log_path.read_text(encoding="utf-8", errors="replace")
    assert "A" * 6000 in full_output
    assert "B" * 6000 in full_output
    jobs = JobStore(tmp_path).list_jobs(limit=None)
    assert len(jobs) == 1
    assert jobs[0].status == "exited"
    assert jobs[0].command == command
    assert jobs[0].log_path == match.group(1)


@pytest.mark.skipif(sys.platform == "win32", reason="background exec is POSIX-specific")
@pytest.mark.asyncio
async def test_exec_auto_background_commands(tmp_path):
    tool = ExecTool(timeout=1, working_dir=str(tmp_path), background_commands=["sleep"])

    result = await tool.execute(command="sleep 30")

    assert "Background exec started." in result
    pid_line = next(line for line in result.splitlines() if line.startswith("PID: "))
    pid = int(pid_line.split(":", 1)[1].strip())
    os.killpg(pid, signal.SIGTERM)


@pytest.mark.asyncio
async def test_exec_allows_curl_to_public_url():
    """Commands with public URLs should not be blocked by the internal URL check."""
    tool = ExecTool()
    with patch("mlpcopilot.security.network.socket.getaddrinfo", _fake_resolve_public):
        guard_result = tool._guard_command("curl https://example.com/api", "/tmp")
    assert guard_result is None


@pytest.mark.asyncio
async def test_exec_blocks_chained_internal_url():
    """Internal URLs buried in chained commands should still be caught."""
    tool = ExecTool()
    with patch("mlpcopilot.security.network.socket.getaddrinfo", _fake_resolve_private):
        result = await tool.execute(
            command="echo start && curl http://169.254.169.254/latest/meta-data/ && echo done"
        )
    assert "Error" in result


# --- exec approval is not shell-command-pattern detection ----------------


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf victim",
        "echo '{}' > history.jsonl",
        "del /f victim.txt",
        "rmdir /s victim",
        "dd if=/dev/zero of=memory/history.jsonl",
        "python3 -c \"from pathlib import Path; Path('victim.txt').unlink()\"",
    ],
)
def test_exec_default_guard_does_not_special_case_shell_mutations(command):
    tool = ExecTool()
    result = tool._guard_command(command, "/tmp")
    assert result is None


@pytest.mark.parametrize(
    "command",
    [
        "cat history.jsonl",
        "wc -l history.jsonl",
        "tail -n 5 history.jsonl",
        "grep foo history.jsonl",
        "cp history.jsonl /tmp/history.backup",
        "ls memory/",
        "echo history.jsonl",
    ],
)
def test_exec_allows_reads_of_history_jsonl(command):
    """Read-only access to history.jsonl must still be allowed."""
    tool = ExecTool()
    result = tool._guard_command(command, "/tmp")
    assert result is None


# --- #2826: working_dir must not escape the configured workspace ---------


@pytest.mark.asyncio
async def test_exec_blocks_working_dir_outside_workspace(tmp_path):
    """An LLM-supplied working_dir outside the workspace must be rejected."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tool = ExecTool(working_dir=str(workspace), restrict_to_workspace=True)
    result = await tool.execute(command="rm calendar.ics", working_dir="/etc")
    assert "outside the configured workspace" in result


@pytest.mark.asyncio
async def test_exec_blocks_absolute_rm_via_hijacked_working_dir(tmp_path):
    """Regression for #2826: `rm /abs/path` via working_dir hijack."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    victim_dir = tmp_path / "outside"
    victim_dir.mkdir()
    victim = victim_dir / "file.ics"
    victim.write_text("data")

    tool = ExecTool(working_dir=str(workspace), restrict_to_workspace=True)
    result = await tool.execute(
        command=f"rm {victim}",
        working_dir=str(victim_dir),
    )
    assert "outside the configured workspace" in result
    assert victim.exists(), "victim file must not have been deleted"


@pytest.mark.asyncio
async def test_exec_allows_working_dir_within_workspace(tmp_path):
    """A working_dir that is a subdirectory of the workspace is fine."""
    workspace = tmp_path / "workspace"
    subdir = workspace / "project"
    subdir.mkdir(parents=True)
    tool = ExecTool(working_dir=str(workspace), restrict_to_workspace=True, timeout=5)
    result = await tool.execute(command="echo ok", working_dir=str(subdir))
    assert "ok" in result
    assert "outside the configured workspace" not in result


@pytest.mark.asyncio
async def test_exec_allows_working_dir_equal_to_workspace(tmp_path):
    """Passing working_dir equal to the workspace root must be allowed."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tool = ExecTool(working_dir=str(workspace), restrict_to_workspace=True, timeout=5)
    result = await tool.execute(command="echo ok", working_dir=str(workspace))
    assert "ok" in result
    assert "outside the configured workspace" not in result


@pytest.mark.asyncio
async def test_exec_require_allowlist_blocks_empty_allowlist(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tool = ExecTool(
        working_dir=str(workspace),
        restrict_to_workspace=True,
        require_allowlist=True,
    )

    result = await tool.execute(command="echo ok")

    assert "exec allowlist is empty" in result
    assert ApprovalManager(workspace).list_pending() == []


@pytest.mark.asyncio
async def test_exec_empty_allowlist_with_approval_prompts(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tool = ExecTool(
        working_dir=str(workspace),
        restrict_to_workspace=True,
        require_allowlist=True,
        approval_required=True,
    )

    result = await tool.execute(command="echo ok")

    assert "Approval required" in result
    assert ApprovalManager(workspace).list_pending()[0].metadata["command"] == "echo ok"


@pytest.mark.asyncio
async def test_exec_exact_allow_command_runs_without_approval(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tool = ExecTool(
        working_dir=str(workspace),
        restrict_to_workspace=True,
        allow_commands=["echo ok"],
        require_allowlist=True,
        approval_required=True,
        timeout=5,
    )

    result = await tool.execute(command="echo ok")

    assert "ok" in result
    assert ApprovalManager(workspace).list_pending() == []


@pytest.mark.asyncio
async def test_exec_non_exact_allow_command_requires_approval(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tool = ExecTool(
        working_dir=str(workspace),
        restrict_to_workspace=True,
        allow_commands=["echo ok"],
        require_allowlist=True,
        approval_required=True,
        timeout=5,
    )

    blocked = await tool.execute(command="echo  ok")
    pending = ApprovalManager(workspace).list_pending()

    assert "Approval required" in blocked
    assert len(pending) == 1
    assert pending[0].action_type == "exec_command"
    assert pending[0].metadata["command"] == "echo  ok"

    ApprovalManager(workspace).approve(pending[0].approval_id, decided_by="test")
    result = await tool.execute(command="echo  ok", approval_id=pending[0].approval_id)

    assert "ok" in result
    assert "Exit code: 0" in result


@pytest.mark.asyncio
async def test_exec_readonly_command_name_runs_without_exact_approval(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "file.txt").write_text("x", encoding="utf-8")
    tool = ExecTool(
        working_dir=str(workspace),
        restrict_to_workspace=True,
        readonly_commands=["ls"],
        require_allowlist=True,
        approval_required=True,
        timeout=5,
    )

    result = await tool.execute(command="ls -al .")

    assert "file.txt" in result
    assert ApprovalManager(workspace).list_pending() == []


@pytest.mark.asyncio
async def test_exec_readonly_command_rejects_shell_mutation_syntax(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tool = ExecTool(
        working_dir=str(workspace),
        restrict_to_workspace=True,
        readonly_commands=["ls"],
        require_allowlist=True,
        approval_required=True,
        timeout=5,
    )

    result = await tool.execute(command="ls > out.txt")

    assert "Approval required" in result
    assert ApprovalManager(workspace).list_pending()[0].metadata["command"] == "ls > out.txt"
    assert not (workspace / "out.txt").exists()


@pytest.mark.asyncio
async def test_exec_readonly_command_allows_safe_probe_chain(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tool = ExecTool(
        working_dir=str(workspace),
        restrict_to_workspace=True,
        readonly_commands=["which"],
        require_allowlist=True,
        approval_required=True,
        timeout=5,
    )

    result = await tool.execute(command='which definitely_missing_cmd 2>/dev/null || echo "not found"')

    assert "not found" in result
    assert ApprovalManager(workspace).list_pending() == []


@pytest.mark.asyncio
async def test_exec_readonly_command_rejects_mixed_mutating_chain(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "victim.txt").write_text("data", encoding="utf-8")
    tool = ExecTool(
        working_dir=str(workspace),
        restrict_to_workspace=True,
        readonly_commands=["cat"],
        require_allowlist=True,
        approval_required=True,
        timeout=5,
    )

    result = await tool.execute(command="cat victim.txt && rm victim.txt")

    assert "Approval required" in result
    assert (workspace / "victim.txt").exists()


@pytest.mark.asyncio
async def test_exec_readonly_command_rejects_non_devnull_redirect(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tool = ExecTool(
        working_dir=str(workspace),
        restrict_to_workspace=True,
        readonly_commands=["which"],
        require_allowlist=True,
        approval_required=True,
        timeout=5,
    )

    result = await tool.execute(command='which missing 2>probe.log || echo "not found"')

    assert "Approval required" in result
    assert not (workspace / "probe.log").exists()


@pytest.mark.asyncio
async def test_exec_echo_alone_is_not_readonly(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tool = ExecTool(
        working_dir=str(workspace),
        restrict_to_workspace=True,
        readonly_commands=["which"],
        require_allowlist=True,
        approval_required=True,
        timeout=5,
    )

    result = await tool.execute(command="echo hello")

    assert "Approval required" in result


@pytest.mark.asyncio
async def test_exec_echo_redirect_is_not_readonly(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tool = ExecTool(
        working_dir=str(workspace),
        restrict_to_workspace=True,
        readonly_commands=["which"],
        require_allowlist=True,
        approval_required=True,
        timeout=5,
    )

    result = await tool.execute(command="echo hello > out.txt")

    assert "Approval required" in result
    assert not (workspace / "out.txt").exists()


@pytest.mark.asyncio
async def test_exec_readonly_command_still_respects_workspace_boundary(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    tool = ExecTool(
        working_dir=str(workspace),
        restrict_to_workspace=True,
        readonly_commands=["ls"],
        require_allowlist=True,
        approval_required=True,
        timeout=5,
    )

    result = await tool.execute(command=f"ls {outside}")

    assert "outside working dir" in result
    assert ApprovalManager(workspace).list_pending() == []


@pytest.mark.asyncio
async def test_exec_approval_required_blocks_until_approved(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tool = ExecTool(
        working_dir=str(workspace),
        restrict_to_workspace=True,
        allow_patterns=[r"^echo\b"],
        require_allowlist=True,
        approval_required=True,
        timeout=5,
    )

    blocked = await tool.execute(command="echo ok")
    pending = ApprovalManager(workspace).list_pending()

    assert "Approval required" in blocked
    assert len(pending) == 1
    assert pending[0].action_type == "exec_command"
    assert pending[0].metadata["command"] == "echo ok"

    ApprovalManager(workspace).approve(pending[0].approval_id, decided_by="test")
    result = await tool.execute(command="echo ok", approval_id=pending[0].approval_id)

    assert "ok" in result
    assert "Exit code: 0" in result


@pytest.mark.asyncio
async def test_exec_approved_decision_does_not_authorize_future_calls(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tool = ExecTool(
        working_dir=str(workspace),
        restrict_to_workspace=True,
        allow_patterns=[r"^echo\b"],
        require_allowlist=True,
        approval_required=True,
        timeout=5,
    )

    blocked = await tool.execute(command="echo ok")
    first = ApprovalManager(workspace).list_pending()[0]
    ApprovalManager(workspace).approve(first.approval_id, decided_by="test")
    result = await tool.execute(command="echo ok", approval_id=first.approval_id)

    blocked_again = await tool.execute(command="echo ok")
    pending = ApprovalManager(workspace).list_pending()

    assert "Approval required" in blocked
    assert "Exit code: 0" in result
    assert "Approval required" in blocked_again
    assert len(pending) == 1
    assert pending[0].approval_id != first.approval_id


@pytest.mark.asyncio
async def test_exec_approval_id_cannot_be_reused_for_different_command(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tool = ExecTool(
        working_dir=str(workspace),
        restrict_to_workspace=True,
        allow_patterns=[r"^echo\b"],
        require_allowlist=True,
        approval_required=True,
        timeout=5,
    )
    await tool.execute(command="echo one")
    approval = ApprovalManager(workspace).list_pending()[0]
    ApprovalManager(workspace).approve(approval.approval_id, decided_by="test")

    result = await tool.execute(command="echo two", approval_id=approval.approval_id)

    assert "different command" in result


@pytest.mark.asyncio
async def test_exec_approval_required_applies_to_rm_without_shell_special_case(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    victim = workspace / "victim.txt"
    victim.write_text("data", encoding="utf-8")
    tool = ExecTool(
        working_dir=str(workspace),
        restrict_to_workspace=True,
        approval_required=True,
        timeout=5,
    )

    blocked = await tool.execute(command="rm -f victim.txt")
    pending = ApprovalManager(workspace).list_pending()

    assert "Approval required" in blocked
    assert victim.exists()
    assert len(pending) == 1
    assert pending[0].action_type == "exec_command"
    assert pending[0].metadata["command"] == "rm -f victim.txt"
    assert "destructive" not in pending[0].metadata

    ApprovalManager(workspace).approve(pending[0].approval_id, decided_by="test")
    result = await tool.execute(command="rm -f victim.txt", approval_id=pending[0].approval_id)

    assert "Exit code: 0" in result
    assert not victim.exists()


@pytest.mark.asyncio
async def test_exec_approval_required_applies_to_recursive_rm(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    victim = workspace / "victim"
    victim.mkdir()
    (victim / "file.txt").write_text("data", encoding="utf-8")
    tool = ExecTool(
        working_dir=str(workspace),
        restrict_to_workspace=True,
        approval_required=True,
        timeout=5,
    )

    blocked = await tool.execute(command="rm -rf victim")
    pending = ApprovalManager(workspace).list_pending()

    assert "Approval required" in blocked
    assert victim.exists()
    assert len(pending) == 1
    assert pending[0].action_type == "exec_command"
    assert pending[0].metadata["command"] == "rm -rf victim"

    ApprovalManager(workspace).approve(pending[0].approval_id, decided_by="test")
    result = await tool.execute(command="rm -rf victim", approval_id=pending[0].approval_id)

    assert "Exit code: 0" in result
    assert not victim.exists()


@pytest.mark.asyncio
async def test_exec_approval_required_applies_to_any_shell_program(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    victim = workspace / "victim.txt"
    victim.write_text("data", encoding="utf-8")
    command = "python3 -c \"from pathlib import Path; Path('victim.txt').unlink()\""
    tool = ExecTool(
        working_dir=str(workspace),
        restrict_to_workspace=True,
        approval_required=True,
        timeout=5,
    )

    blocked = await tool.execute(command=command)
    pending = ApprovalManager(workspace).list_pending()

    assert "Approval required" in blocked
    assert victim.exists()
    assert len(pending) == 1
    assert pending[0].action_type == "exec_command"
    assert pending[0].metadata["command"] == command

    ApprovalManager(workspace).approve(pending[0].approval_id, decided_by="test")
    result = await tool.execute(command=command, approval_id=pending[0].approval_id)

    assert "Exit code: 0" in result
    assert not victim.exists()


@pytest.mark.asyncio
async def test_exec_ignores_workspace_check_when_not_restricted(tmp_path):
    """Without restrict_to_workspace, the LLM may still choose any working_dir."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    tool = ExecTool(working_dir=str(workspace), restrict_to_workspace=False, timeout=5)
    result = await tool.execute(command="echo ok", working_dir=str(other))
    assert "ok" in result
    assert "outside the configured workspace" not in result
