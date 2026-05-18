from .common import *  # noqa: F403


def test_tui_input_controller_queues_normal_input(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    state = RuntimeTuiState()
    queue = _FakeQueue()
    controller = TuiInputController(
        config=config,
        state=state,
        queue=queue,
        app_ref={},
    )

    controller.submit("hello")

    assert queue.items == ["hello"]
    assert state.queued_count == 1

def test_tui_input_controller_bang_command_bypasses_pending_approval_block(tmp_path) -> None:
    sync_mlpcopilot_workspace(tmp_path, silent=True)
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    ApprovalManager(tmp_path).create(
        action_type="exec_command",
        title="Run command",
        request="Run command",
        metadata={"tool": "exec", "command": "ls", "working_dir": str(tmp_path)},
    )
    state = RuntimeTuiState()
    queue = _FakeQueue()
    controller = TuiInputController(
        config=config,
        state=state,
        queue=queue,
        app_ref={},
    )

    controller.submit("!sleep 0")

    assert queue.items == ["!sleep 0"]
    assert state.chat == []

def test_tui_input_controller_stop_cancels_active_task(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    state = RuntimeTuiState()
    task = _FakeTask()
    queue = _FakeQueue()
    controller = TuiInputController(
        config=config,
        state=state,
        queue=queue,
        app_ref={},
        active_turn_task={"task": task},
    )

    controller.submit("/stop")

    assert task.cancelled is True
    assert queue.items == []
    assert state.chat[-1].content == "Stop requested. Waiting for the current tool to terminate..."

def test_tui_input_controller_stop_job_persists_tool_log(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "mlpcopilot.runtime.jobs.os.killpg",
        lambda _process_group, _sig: None,
        raising=False,
    )
    job = JobStore(tmp_path).record_start(
        kind="exec",
        command="cmatrix",
        pid=os.getpid(),
        process_group=12345,
        cwd=str(tmp_path),
        log_path=tmp_path / "jobs" / "exec_demo.log",
    )
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    state = RuntimeTuiState()
    controller = TuiInputController(
        config=config,
        state=state,
        queue=_FakeQueue(),
        app_ref={},
    )

    controller.submit(f"/stop {job.job_id}")

    loaded = load_persisted_tool_log(tmp_path, session_id=state.active_session_id)
    assert loaded[-1].name == "exec"
    assert loaded[-1].status == "stopped"
    assert loaded[-1].detail == "cmatrix"

async def test_tui_input_controller_handles_approval_without_queueing(tmp_path) -> None:
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
    exec_tool = _FakeExecTool()
    loop = _FakeLoop(tmp_path, exec_tool=exec_tool)
    state = RuntimeTuiState(running=True)
    queue = _FakeQueue()
    controller = TuiInputController(
        config=config,
        state=state,
        queue=queue,
        app_ref={},
        agent_loop=loop,
    )

    controller.submit(f"/approve {approval.approval_id}")
    await asyncio.gather(*controller.immediate_tasks)

    assert len(queue.items) == 1
    assert isinstance(queue.items[0], TuiQueuedInput)
    assert queue.items[0].show_user_message is False
    assert queue.items[0].metadata["_skip_user_persist"] is True
    assert "pending approval decisions" in queue.items[0].content
    assert "stdout" in queue.items[0].content
    assert state.chat[0].content == f"/approve {approval.approval_id}"
    assert "marked approved" in state.chat[1].content
    assert 'exec "ls" completed OK' in state.chat[1].content
    assert exec_tool.calls == [
        {
            "command": "ls",
            "working_dir": str(tmp_path),
            "approval_id": approval.approval_id,
        }
    ]
    assert load_persisted_tool_log(tmp_path, session_id=state.active_session_id)[0].detail == "ls"

async def test_tui_input_controller_batches_multiple_approvals_before_continuing(tmp_path) -> None:
    sync_mlpcopilot_workspace(tmp_path, silent=True)
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    manager = ApprovalManager(tmp_path)
    first = manager.create(
        action_type="exec_command",
        title="Run ls",
        request="Run ls",
        metadata={"tool": "exec", "command": "ls", "working_dir": str(tmp_path)},
    )
    second = manager.create(
        action_type="exec_command",
        title="Run pwd",
        request="Run pwd",
        metadata={"tool": "exec", "command": "pwd", "working_dir": str(tmp_path)},
    )
    loop = _FakeLoop(tmp_path, exec_tool=_FakeExecTool())
    state = RuntimeTuiState()
    queue = _FakeQueue()
    controller = TuiInputController(
        config=config,
        state=state,
        queue=queue,
        app_ref={},
        agent_loop=loop,
    )

    controller.submit(f"/approve {first.approval_id}")
    await asyncio.gather(*controller.immediate_tasks)

    assert queue.items == []
    assert len(state.approval_continuation_results) == 1
    assert 'exec "ls" completed OK' in state.approval_continuation_results[0]

    controller.submit(f"/approve {second.approval_id}")
    await asyncio.gather(*controller.immediate_tasks)

    assert len(queue.items) == 1
    assert isinstance(queue.items[0], TuiQueuedInput)
    assert queue.items[0].show_user_message is False
    assert 'exec "ls" completed OK' in queue.items[0].content
    assert 'exec "pwd" completed OK' in queue.items[0].content
    assert state.approval_continuation_results == []

def test_tui_input_controller_handles_local_command_without_queueing(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    state = RuntimeTuiState(running=True)
    queue = _FakeQueue()
    controller = TuiInputController(config=config, state=state, queue=queue, app_ref={})

    controller.submit("/status")

    assert queue.items == []
    assert state.chat[0].role == "user"
    assert state.chat[0].content == "/status"
    assert state.chat[1].role == "system"
    assert f"profile=mlpcopilot workspace={tmp_path}" in state.chat[-1].content
    assert "writes=" in state.chat[-1].content
    assert "tools=" in state.chat[-1].content

def test_tui_input_controller_queues_plan_for_async_summary(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    state = RuntimeTuiState()
    queue = _FakeQueue()
    controller = TuiInputController(
        config=config,
        state=state,
        queue=queue,
        app_ref={},
    )

    controller.submit("/plan add revise validation")

    assert queue.items == ["/plan add revise validation"]
    assert state.chat == []

def test_tui_input_controller_handles_history_without_queueing(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    state = RuntimeTuiState(running=True)
    state.add_chat("user", "hello")
    state.add_chat("assistant", "world")
    queue = _FakeQueue()
    controller = TuiInputController(config=config, state=state, queue=queue, app_ref={})

    controller.submit("/history")

    assert queue.items == []
    assert state.chat[-2].content == "/history"
    assert "Recent history (2/2):" in state.chat[-1].content

def test_tui_input_controller_switches_model_without_queueing(tmp_path) -> None:
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
    state = RuntimeTuiState()
    queue = _FakeQueue()
    controller = TuiInputController(
        config=config,
        state=state,
        queue=queue,
        app_ref={},
        agent_loop=loop,
    )

    controller.submit("/model openai-codex/gpt-5.3-codex")

    assert queue.items == []
    assert config.agents.defaults.model == "openai-codex/gpt-5.3-codex"
    assert loop.model == "openai-codex/gpt-5.3-codex"
    assert state.chat[-1].content == (
        "Model switched: openai-codex/gpt-5.4-mini -> openai-codex/gpt-5.3-codex"
    )

def test_tui_input_controller_blocks_model_switch_while_running(tmp_path) -> None:
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
    state = RuntimeTuiState(running=True)
    queue = _FakeQueue()
    controller = TuiInputController(
        config=config,
        state=state,
        queue=queue,
        app_ref={},
        agent_loop=loop,
    )

    controller.submit("/model openai-codex/gpt-5.3-codex")

    assert queue.items == []
    assert config.agents.defaults.model == "openai-codex/gpt-5.4-mini"
    assert [(message.role, message.content) for message in state.chat] == [
        ("system", "/model is disabled while a task is running.")
    ]

def test_tui_input_controller_blocks_agent_slash_while_running(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    state = RuntimeTuiState(running=True)
    queue = _FakeQueue()
    controller = TuiInputController(config=config, state=state, queue=queue, app_ref={})

    controller.submit("/plan revise validation")

    assert queue.items == []
    assert [(message.role, message.content) for message in state.chat] == [
        ("system", "/plan is disabled while a task is running.")
    ]

def test_tui_input_controller_blocks_noncritical_local_command_during_approval(tmp_path) -> None:
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
    )
    state = RuntimeTuiState()
    queue = _FakeQueue()
    controller = TuiInputController(config=config, state=state, queue=queue, app_ref={})

    controller.submit("/runs")

    assert queue.items == []
    assert len(state.chat) == 1
    assert state.chat[0].role == "system"
    assert approval.approval_id in state.chat[0].content

def test_tui_input_controller_handles_tool_log_alias_without_queueing(tmp_path) -> None:
    state = RuntimeTuiState(running=True)
    save_persisted_tool_log(
        tmp_path,
        [ToolLogEntry(name="exec", status="ok", detail="ls", duration_s=0.01)],
        session_id=state.active_session_id,
    )
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    queue = _FakeQueue()
    controller = TuiInputController(config=config, state=state, queue=queue, app_ref={})

    controller.submit("/toollog")

    assert queue.items == []
    assert state.chat[0].content == "/toollog"
    assert state.chat[1].role == "system"
    assert "Recent tool log:" in state.chat[1].content

def test_tui_input_controller_rejects_unknown_slash_without_queueing(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    state = RuntimeTuiState(running=True)
    queue = _FakeQueue()
    controller = TuiInputController(config=config, state=state, queue=queue, app_ref={})

    controller.submit("/does-not-exist")

    assert queue.items == []
    assert [(message.role, message.content) for message in state.chat] == [
        ("user", "/does-not-exist"),
        ("system", "Unknown command: /does-not-exist. Use /help."),
    ]

def test_tui_input_controller_switches_selected_layout(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    state = RuntimeTuiState(layout_name="four_pane", layout_picker_selection=1)
    controller = TuiInputController(
        config=config,
        state=state,
        queue=_FakeQueue(),
        app_ref={},
    )

    controller.open_layout_picker()
    controller.move_layout_picker_selection(1)
    controller.accept_layout_picker_selection()

    assert state.layout_name == "compact"
    assert state.overlay_stack == []
    assert state.chat[-1].content == "Layout switched: four_pane -> compact"
    assert load_tui_state(tmp_path)["layout_name"] == "compact"

def test_tui_input_controller_switches_selected_model(tmp_path) -> None:
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
    state = RuntimeTuiState()
    loop = _FakeLoop(tmp_path)
    controller = TuiInputController(
        config=config,
        state=state,
        queue=_FakeQueue(),
        app_ref={},
        agent_loop=loop,
    )

    controller.open_model_picker()
    controller.move_model_picker_selection(1)
    controller.accept_model_picker_selection()

    assert config.agents.defaults.model == "openai-codex/gpt-5.3-codex"
    assert loop.model == "openai-codex/gpt-5.3-codex"
    assert state.overlay_stack == []
    assert state.chat[-1].content == (
        "Model switched: openai-codex/gpt-5.4-mini -> openai-codex/gpt-5.3-codex"
    )
