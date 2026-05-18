from mlpcopilot.providers.base import LLMResponse

from .common import *  # noqa: F403


def test_tui_runtime_factory_uses_unavailable_provider(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path), "model": "test/model"}},
        }
    )

    runtime = build_tui_agent_loop(
        config=config,
        provider=None,
        provider_error="missing key",
    )

    assert isinstance(runtime.agent_loop.provider, TuiUnavailableProvider)
    assert runtime.agent_loop.provider.reason == "missing key"
    assert runtime.provider_notice is not None
    assert "missing key" in runtime.provider_notice
    assert runtime.provider_notice_reason == "missing key"

async def test_tui_runtime_controller_processes_local_command(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    state = RuntimeTuiState()
    queue = asyncio.Queue()
    loop = _FakeLoop(tmp_path)
    controller = TuiRuntimeController(
        config=config,
        state=state,
        agent_loop=loop,
        session_id="tui:default",
        queue=queue,
        app_ref={},
    )

    queue.put_nowait("/status")
    worker = asyncio.create_task(controller.run_worker())
    await queue.join()
    worker.cancel()
    await asyncio.gather(worker, return_exceptions=True)

    assert [message.role for message in state.chat[-2:]] == ["user", "system"]
    assert state.chat[-2].content == "/status"
    assert "profile=mlpcopilot" in state.chat[-1].content
    assert state.running is False
    assert state.current_input == ""
    assert controller.active_turn_task["task"] is None

async def test_tui_runtime_controller_runs_bang_shell_command(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    state = RuntimeTuiState()
    queue = asyncio.Queue()
    loop = _FakeLoop(tmp_path)
    controller = TuiRuntimeController(
        config=config,
        state=state,
        agent_loop=loop,
        session_id="tui:default",
        queue=queue,
        app_ref={},
    )

    queue.put_nowait("!printf 'hello\\n'")
    worker = asyncio.create_task(controller.run_worker())
    await queue.join()
    worker.cancel()
    await asyncio.gather(worker, return_exceptions=True)

    assert [message.role for message in state.chat[-2:]] == ["user", "system"]
    assert state.chat[-2].content == "!printf 'hello\\n'"
    assert "Shell command completed OK: printf 'hello\\n'" in state.chat[-1].content
    assert "stdout:\nhello" in state.chat[-1].content
    assert len(state.tool_log) == 1
    assert state.tool_log[0].name == "shell"
    assert state.tool_log[0].status == "ok"
    assert state.tool_log[0].detail == "printf 'hello\\n'"
    assert state.tool_log[0].duration_s is not None

async def test_tui_line_fallback_bang_shell_bypasses_approval_block(tmp_path) -> None:
    from mlpcopilot.runtime.tui.input.line_fallback import _run_line_fallback

    sync_mlpcopilot_workspace(tmp_path, silent=True)
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    ApprovalManager(tmp_path).create(
        action_type="exec_command",
        title="Run gated command",
        request="Run gated command",
    )
    state = RuntimeTuiState()
    queue = asyncio.Queue()
    loop = _FakeLoop(tmp_path)
    controller = TuiRuntimeController(
        config=config,
        state=state,
        agent_loop=loop,
        session_id="tui:default",
        queue=queue,
        app_ref={},
    )
    console = _FakeLineConsole(["!printf 'fallback\\n'"])

    await _run_line_fallback(config, state, queue, console, controller.run_worker)

    assert [message.role for message in state.chat[-2:]] == ["user", "system"]
    assert state.chat[-2].content == "!printf 'fallback\\n'"
    assert "Shell command completed OK: printf 'fallback\\n'" in state.chat[-1].content
    assert "stdout:\nfallback" in state.chat[-1].content

def test_tui_runtime_command_decides_approval(tmp_path) -> None:
    sync_mlpcopilot_workspace(tmp_path, silent=True)
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    approval = ApprovalManager(tmp_path).create(
        action_type="exec_command",
        title="Run pytest",
        request="pytest tests",
    )

    result = handle_tui_runtime_command(config, f"/approve {approval.approval_id} ok")

    assert result == f"Approval {approval.approval_id} marked approved"
    assert ApprovalManager(tmp_path).list_pending() == []

def test_tui_runtime_command_hints_bare_approval_id(tmp_path) -> None:
    sync_mlpcopilot_workspace(tmp_path, silent=True)
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    approval = ApprovalManager(tmp_path).create(
        action_type="exec_command",
        title="Run delete",
        request="Delete a file",
    )

    result = handle_tui_runtime_command(config, approval.approval_id)

    assert result == (
        "Approval ID detected. Use "
        f"/approve {approval.approval_id}, /reject {approval.approval_id}, "
        f"or /changes {approval.approval_id}."
    )
    assert ApprovalManager(tmp_path).list_pending()[0].approval_id == approval.approval_id

async def test_tui_dispatches_shared_slash_commands(tmp_path) -> None:
    sync_mlpcopilot_workspace(tmp_path, silent=True)
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    approval = ApprovalManager(tmp_path).create(
        action_type="exec_command",
        title="Run delete",
        request="Delete a file",
    )
    loop = _FakeLoop(tmp_path)

    result = await dispatch_tui_command(config, loop, "tui:default", "/approvals")

    assert result is not None
    assert "Pending approvals" in result
    assert approval.approval_id in result

async def test_tui_dispatch_rejects_unknown_slash_before_agent_router(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    loop = _FakeLoop(tmp_path)

    result = await dispatch_tui_command(config, loop, "tui:default", "/does-not-exist")

    assert result == "Unknown command: /does-not-exist. Use /help."

async def test_tui_dispatch_handles_goal_and_plan_locally(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    loop = _FakeLoop(tmp_path)

    goal = await dispatch_tui_command(
        config,
        loop,
        "tui:default",
        "/goal finish local validation",
    )
    plan = await dispatch_tui_command(
        config,
        loop,
        "tui:default",
        "/plan add inspect training logs",
    )
    session = loop.sessions.get_or_create("tui:default")

    assert goal == (
        "Goal set:\nfinish local validation\n"
        "Summary: AI refresh running in background."
    )
    assert plan is not None
    assert "1. [pending] inspect training logs" in plan
    assert "Summary: AI refresh running in background." in plan
    assert session.metadata["_work_goal"] == "finish local validation"
    assert session.metadata["_work_plan"][0]["step"] == "inspect training logs"
    assert session.metadata["_work_goal_summary"] == "finish local validation"
    assert session.metadata["_work_plan_summary"] == "inspect training logs"


async def test_tui_dispatch_handles_active_project_pointer(tmp_path) -> None:
    from mlpcopilot.runtime.workspace import create_mlp_project, create_mlp_run

    create_mlp_project(tmp_path, name="local", project_id="local_dpgen")
    create_mlp_run(tmp_path, "local_dpgen", run_id="run_local")
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    loop = _FakeLoop(tmp_path)

    result = await dispatch_tui_command(
        config,
        loop,
        "tui:default",
        "/project set local_dpgen",
    )
    session = loop.sessions.get_or_create("tui:default")

    assert result is not None
    assert "Active project set" in result
    assert "project_id: local_dpgen" in result
    assert "run_id: run_local" in result
    assert session.metadata["_active_mlp_project"]["backend"] == "dpgen"


async def test_tui_dispatch_handles_memory_audit_locally(tmp_path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / "MEMORY.md").write_text(
        "- Current status: iter.000021 stage0 make_train.\n",
        encoding="utf-8",
    )
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    loop = _FakeLoop(tmp_path)

    result = await dispatch_tui_command(config, loop, "tui:default", "/memory-audit")

    assert result is not None
    assert "Memory audit" in result
    assert "dpgen-iteration" in result


async def test_tui_dispatch_goal_uses_ai_summary(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    loop = _FakeLoop(tmp_path)
    loop.provider = _FakeSummaryProvider("主动学习检查")
    scheduled = []
    loop._schedule_background = scheduled.append

    goal = await dispatch_tui_command(
        config,
        loop,
        "tui:default",
        "/goal 告诉我的妈妈的一个朋友的儿子一盒testjk",
    )
    assert goal == (
        "Goal set:\n告诉我的妈妈的一个朋友的儿子一盒testjk\n"
        "Summary: AI refresh running in background."
    )
    assert len(scheduled) == 1
    await scheduled[0]
    session = loop.sessions.get_or_create("tui:default")

    assert session.metadata["_work_goal_summary"] == "主动学习检查"

async def test_tui_dispatch_handles_session_command_without_model(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    loop = _FakeLoop(tmp_path)
    session = loop.sessions.get_or_create("tui:default")
    session.add_message("user", "old")
    loop.sessions.save(session)

    result = await dispatch_tui_command(config, loop, "tui:default", "/new")

    assert result == "New session started."
    assert loop.sessions.get_or_create("tui:default").messages == []

async def test_tui_runtime_controller_resets_visible_state_for_new_session(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    state = RuntimeTuiState(chat_scroll=4, tool_log_pager_scroll=2)
    state.add_chat("assistant", "old visible message")
    state.tool_log.append(ToolLogEntry(name="exec", status="ok", detail="ls"))
    save_persisted_tool_log(
        tmp_path,
        [ToolLogEntry(name="grep", status="ok", detail="old-global-log")],
    )
    queue = asyncio.Queue()
    loop = _FakeLoop(tmp_path)
    session = loop.sessions.get_or_create("tui:default")
    session.add_message("user", "old persisted message")
    loop.sessions.save(session)
    controller = TuiRuntimeController(
        config=config,
        state=state,
        agent_loop=loop,
        session_id="tui:default",
        queue=queue,
        app_ref={},
    )

    queue.put_nowait("/new")
    worker = asyncio.create_task(controller.run_worker())
    await queue.join()
    worker.cancel()
    await asyncio.gather(worker, return_exceptions=True)

    assert [(message.role, message.content) for message in state.chat] == [
        ("system", "New session started.")
    ]
    assert state.tool_log == []
    assert state.chat_scroll == 0
    assert state.tool_log_pager_scroll == 0
    assert loop.sessions.get_or_create("tui:default").messages == []
    assert handle_tui_runtime_command(config, "/tool-log", state=state) == "Tool log: none."

async def test_tui_approve_resumes_exec_action(tmp_path) -> None:
    sync_mlpcopilot_workspace(tmp_path, silent=True)
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    approval = ApprovalManager(tmp_path).create(
        action_type="destructive_exec",
        title="Delete file",
        request="Delete file",
        metadata={
            "tool": "exec",
            "command": "rm to.txt",
            "working_dir": str(tmp_path),
            "destructive": True,
        },
    )
    exec_tool = _FakeExecTool()
    loop = _FakeLoop(tmp_path, exec_tool=exec_tool)
    state = RuntimeTuiState()

    result = await dispatch_tui_command(
        config,
        loop,
        "tui:default",
        f"approve {approval.approval_id}",
        state,
    )

    assert result is not None
    assert f"Approval {approval.approval_id} marked approved" in result
    assert 'exec "rm to.txt" completed OK' in result
    assert "Output:\nstdout" in result
    assert "Exit code: 0" not in result
    assert exec_tool.calls == [
        {
            "command": "rm to.txt",
            "working_dir": str(tmp_path),
            "approval_id": approval.approval_id,
        }
    ]
    assert len(state.tool_log) == 1
    assert state.tool_log[0].status == "ok"
    assert state.tool_log[0].name == "exec"
    assert state.tool_log[0].detail == "rm to.txt"
    assert state.tool_log[0].duration_s is not None

async def test_tui_runtime_controller_auto_continues_after_approved_tool(tmp_path) -> None:
    sync_mlpcopilot_workspace(tmp_path, silent=True)
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    approval = ApprovalManager(tmp_path).create(
        action_type="exec_command",
        title="Run command",
        request="Run command",
        metadata={
            "tool": "exec",
            "command": "ls",
            "working_dir": str(tmp_path),
        },
    )
    loop = _FakeLoop(tmp_path, exec_tool=_FakeExecTool())
    state = RuntimeTuiState()
    queue = asyncio.Queue()
    controller = TuiRuntimeController(
        config=config,
        state=state,
        agent_loop=loop,
        session_id="tui:default",
        queue=queue,
        app_ref={},
    )

    queue.put_nowait(f"/approve {approval.approval_id}")
    worker = asyncio.create_task(controller.run_worker())
    await queue.join()
    worker.cancel()
    await asyncio.gather(worker, return_exceptions=True)

    assert [message.role for message in state.chat] == ["user", "system", "assistant"]
    assert state.chat[0].content == f"/approve {approval.approval_id}"
    assert 'exec "ls" completed OK' in state.chat[1].content
    assert state.chat[2].content == "continued after approval"
    assert len(loop.direct_inputs) == 1
    followup = loop.direct_inputs[0][0]
    assert "pending approval decisions" in followup
    assert "stdout" in followup
    assert "<approval_results>" in followup
    assert loop.direct_inputs[0][1]["metadata"]["_skip_user_persist"] is True

def test_tui_runtime_command_handles_model_locally(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path), "model": "test/model"}},
        }
    )

    assert handle_tui_runtime_command(config, "/model").startswith("Current model: test/model")

def test_tui_runtime_command_handles_layout_locally(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path), "model": "test/model"}},
        }
    )
    state = RuntimeTuiState()

    listing = handle_tui_runtime_command(config, "/layout", state=state)
    switched = handle_tui_runtime_command(config, "/layout compact", state=state)
    compact_state = state.layout_name
    campaign = handle_tui_runtime_command(config, "/layout campaign_focus", state=state)
    campaign_state = state.layout_name
    approval = handle_tui_runtime_command(config, "/layout approval_focus", state=state)
    unknown = handle_tui_runtime_command(config, "/layout missing_layout", state=state)

    assert listing is not None
    assert "Current layout: four_pane" in listing
    assert "Available layouts:" in listing
    assert switched == "Layout switched: four_pane -> compact"
    assert compact_state == "compact"
    assert campaign == "Layout switched: compact -> campaign_focus"
    assert campaign_state == "campaign_focus"
    assert approval == "Layout switched: campaign_focus -> approval_focus"
    assert state.layout_name == "approval_focus"
    assert load_tui_state(tmp_path)["layout_name"] == "approval_focus"
    assert tui_state_path(tmp_path).exists()
    assert unknown == "Unknown layout: missing_layout. Use /layout."

def test_tui_runtime_command_handles_history_locally(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path), "model": "test/model"}},
        }
    )
    state = RuntimeTuiState()
    state.add_chat("user", "first")
    state.add_chat("assistant", "second " * 30)
    state.add_chat("user", "third")

    result = handle_tui_runtime_command(config, "/history 2", state=state)

    assert result is not None
    assert "Recent history (2/3):" in result
    assert "1. user: first" not in result
    assert "2. assistant: second" in result
    assert "3. user: third" in result
    assert "Open the latest full message with Ctrl-T." in result

async def test_tui_model_command_switches_active_runtime(tmp_path) -> None:
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
    loop = _FakeLoop(tmp_path)

    result = await dispatch_tui_command(
        config,
        loop,
        "tui:default",
        "/model openai-codex/gpt-5.3-codex",
    )

    assert result == "Model switched: openai-codex/gpt-5.4-mini -> openai-codex/gpt-5.3-codex"
    assert config.agents.defaults.model == "openai-codex/gpt-5.3-codex"
    assert loop.model == "openai-codex/gpt-5.3-codex"

def test_tui_blocks_chat_input_while_approval_is_pending(tmp_path) -> None:
    sync_mlpcopilot_workspace(tmp_path, silent=True)
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    approval = ApprovalManager(tmp_path).create(
        action_type="exec_command",
        title="Run delete",
        request="Delete a file",
        metadata={"tool": "exec", "command": "rm 1.txt"},
    )

    blocked = _approval_block_message(config, "keep going")

    assert blocked is not None
    assert approval.approval_id in blocked
    assert "/approve" in blocked
    assert _approval_block_message(config, f"/approve {approval.approval_id}") is None
    assert _approval_block_message(config, "/status") is None
    assert _approval_block_message(config, "/help") is None
    assert _approval_block_message(config, "/runs") is not None
    assert _approval_block_message(config, "/model other/model") is not None

def test_tui_runtime_command_handles_profile_locally(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )

    assert handle_tui_runtime_command(config, "/profile") == (
        "Current profile: mlpcopilot. "
        "Profiles are selected by config file; start TUI with mlpcopilot tui -c <config>."
    )

def test_tui_runtime_command_handles_runs_and_artifacts_locally(tmp_path) -> None:
    ArtifactIndex(tmp_path).create_run(
        run_id="run_local",
        source="mcp:test:tool",
        artifacts=[
            {
                "artifact_id": "art_report",
                "type": "report",
                "path": "runs/run_local/report.md",
                "sha256": "abcdef1234567890",
                "produced_by": "mcp:test:tool",
            }
        ],
        metrics=[
            {
                "name": "force_rmse",
                "value": 0.08,
                "unit": "eV/A",
                "source_artifact": "art_report",
            }
        ],
        lineage={"parents": ["run_parent"], "inputs": [{"path": "datasets/a.extxyz"}]},
        decisions=[{"approval_id": "apr_1", "status": "approved"}],
        approval={"approval_id": "apr_1", "status": "approved"},
        outputs=[{"metric": "ok"}],
    )
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )

    runs = handle_tui_runtime_command(config, "/runs")
    artifacts = handle_tui_runtime_command(config, "/artifacts run_local")

    assert runs is not None
    assert "Recent runs:" in runs
    assert "run_local" in runs
    assert "source=mcp:test:tool" in runs
    assert "artifacts=1" in runs
    assert "metrics=1" in runs
    assert "decisions=1" in runs
    assert "approval=approved" in runs
    assert artifacts is not None
    assert "Artifacts for run_local:" in artifacts
    assert "art_report report" in artifacts
    assert "runs/run_local/report.md" in artifacts
    assert "sha256=abcdef123456" in artifacts
    assert "producer=mcp:test:tool" in artifacts
    assert "Metrics:" in artifacts
    assert "force_rmse=0.08 eV/A source=art_report" in artifacts
    assert "Lineage:" in artifacts
    assert "parents=run_parent" in artifacts
    assert "inputs=1 first=datasets/a.extxyz" in artifacts
    assert "Decisions:" in artifacts
    assert "apr_1 approved" in artifacts
    assert "Outputs:" in artifacts
    assert '{"metric": "ok"}' in artifacts

def test_tui_runtime_command_handles_jobs_locally(tmp_path) -> None:
    JobStore(tmp_path).record_start(
        kind="exec",
        command="cmatrix",
        pid=os.getpid(),
        process_group=os.getpid(),
        cwd=str(tmp_path),
        log_path=tmp_path / "jobs" / "exec_demo.log",
    )
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )

    result = handle_tui_runtime_command(config, "/ps")

    assert result is not None
    assert "Recent jobs:" in result
    assert "running exec cmatrix" in result
    assert "log=jobs/exec_demo.log" in result

def test_tui_runtime_command_handles_jobs_alias(tmp_path) -> None:
    JobStore(tmp_path).record_start(
        kind="exec",
        command="cmatrix",
        pid=os.getpid(),
        process_group=os.getpid(),
        cwd=str(tmp_path),
        log_path=tmp_path / "jobs" / "exec_demo.log",
    )
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )

    result = handle_tui_runtime_command(config, "/jobs")

    assert result is not None
    assert "Recent jobs:" in result
    assert "cmatrix" in result

def test_tui_runtime_command_handles_tool_log_locally(tmp_path) -> None:
    entries = [
        ToolLogEntry(name="exec", status="ok", detail="ls -la", duration_s=0.03),
        ToolLogEntry(
            name="mcp_agentic_search",
            status="ok",
            detail="task=inspect db",
            call_id="call_raw",
            raw_path="logs/raw-tool-results/call_raw.txt",
        ),
    ]
    save_persisted_tool_log(tmp_path, entries)
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )

    result = handle_tui_runtime_command(config, "/tool-log")

    assert result is not None
    assert "Recent tool log:" in result
    assert "Datetime" in result
    assert "OK" in result
    assert '"ls -la"' in result
    assert "task=inspect db" in result
    assert "Raw results: /raw [last|call_id]" in result
    assert "Full log: logs/tool-log.jsonl" in result

def test_tui_runtime_command_handles_raw_tool_result(tmp_path) -> None:
    raw_path = tmp_path / "logs" / "raw-tool-results" / "call_raw.txt"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_text('{"answer": "ok", "raw": [1, 2, 3]}', encoding="utf-8")
    state = RuntimeTuiState()
    state.tool_log.append(
        ToolLogEntry(
            name="mcp_agentic_search",
            status="ok",
            detail="task=inspect db",
            call_id="call_raw",
            raw_path="logs/raw-tool-results/call_raw.txt",
        )
    )
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )

    result = handle_tui_runtime_command(config, "/raw", state=state)

    assert result is not None
    assert "Raw tool result for mcp_agentic_search call_id=call_raw" in result
    assert "Path: logs/raw-tool-results/call_raw.txt" in result
    assert '"raw": [1, 2, 3]' in result

def test_tui_runtime_command_handles_raw_tool_result_selector(tmp_path) -> None:
    first = tmp_path / "logs" / "raw-tool-results" / "first.txt"
    second = tmp_path / "logs" / "raw-tool-results" / "second.txt"
    first.parent.mkdir(parents=True)
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")
    state = RuntimeTuiState()
    state.tool_log.extend(
        [
            ToolLogEntry(name="mcp_first", status="ok", call_id="call_first", raw_path="logs/raw-tool-results/first.txt"),
            ToolLogEntry(name="mcp_second", status="ok", call_id="call_second", raw_path="logs/raw-tool-results/second.txt"),
        ]
    )
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )

    result = handle_tui_runtime_command(config, "/raw call_first", state=state)

    assert result is not None
    assert "mcp_first" in result
    assert "first" in result
    assert "second" not in result


class _FakeSummaryProvider:
    def __init__(self, content: str) -> None:
        self.content = content

    async def chat_with_retry(self, **_kwargs) -> LLMResponse:
        return LLMResponse(content=self.content)


class _FakeLineConsole:
    def __init__(self, inputs: list[str]) -> None:
        self.inputs = list(inputs)
        self.rendered: list[object] = []

    def clear(self) -> None:
        return None

    def print(self, value: object) -> None:
        self.rendered.append(value)

    def input(self, _prompt: str) -> str:
        if not self.inputs:
            raise EOFError
        return self.inputs.pop(0)
