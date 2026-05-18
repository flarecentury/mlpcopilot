import contextlib

from mlpcopilot.agent.tools.shell import ExecTool

from .common import *  # noqa: F403


def test_tui_job_picker_renders_selectable_jobs(tmp_path) -> None:
    job = JobStore(tmp_path).record_start(
        kind="exec",
        command="cmatrix",
        pid=os.getpid(),
        process_group=os.getpid(),
        cwd=str(tmp_path),
        log_path=tmp_path / "jobs" / "exec_demo.log",
    )
    state = RuntimeTuiState()

    output = _render_job_picker_ansi(
        state,
        JobStore(tmp_path).list_jobs(limit=20),
        width=100,
        height=8,
    )

    assert "jobs | Up/Down select" in output
    assert "> running" in output
    assert job.job_id in output
    assert "cmatrix" in output


def test_job_store_reconcile_stale_marks_dead_pid_exited(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("mlpcopilot.runtime.jobs._pid_exists", lambda _pid: False)
    store = JobStore(tmp_path)
    job = store.record_start(
        kind="exec",
        command="sleep 99",
        pid=999999,
        process_group=999999,
        cwd=str(tmp_path),
    )

    changed = store.reconcile_stale()

    assert [item.job_id for item in changed] == [job.job_id]
    assert changed[0].status == "exited"
    assert JobStore(tmp_path).get(job.job_id).status == "exited"


def test_job_store_startup_reconcile_marks_missing_pid_failed(tmp_path) -> None:
    store = JobStore(tmp_path)
    job = store.record_start(
        kind="exec",
        command="sleep 99",
        pid=None,
        cwd=str(tmp_path),
    )

    assert store.reconcile_stale() == []

    changed = store.reconcile_stale(mark_missing_pid=True)

    assert [item.job_id for item in changed] == [job.job_id]
    assert changed[0].status == "failed"
    assert changed[0].error == "missing pid during startup reconcile"
    assert JobStore(tmp_path).get(job.job_id).status == "failed"


def test_render_tui_reconciles_stale_jobs_on_snapshot(tmp_path) -> None:
    store = JobStore(tmp_path)
    job = store.record_start(
        kind="exec",
        command="sleep 99",
        pid=None,
        cwd=str(tmp_path),
    )
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )

    render_tui(config)

    assert JobStore(tmp_path).get(job.job_id).status == "failed"


def test_tui_input_controller_toggles_job_picker(tmp_path) -> None:
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
    state = RuntimeTuiState()
    controller = TuiInputController(
        config=config,
        state=state,
        queue=_FakeQueue(),
        app_ref={},
    )

    controller.toggle_job_picker()

    assert state.overlay_stack == ["job_picker"]
    assert controller.active_overlay_id() == "job_picker"

    controller.toggle_job_picker()

    assert state.overlay_stack == []

def test_tui_input_controller_reports_empty_job_picker(tmp_path) -> None:
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

    controller.toggle_job_picker()

    assert state.overlay_stack == []
    assert state.chat[-1].content == "Jobs: none."

def test_tui_input_controller_stops_selected_job(tmp_path, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "mlpcopilot.runtime.jobs.os.killpg",
        lambda process_group, sig: calls.append((process_group, sig)),
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

    controller.toggle_job_picker()
    controller.stop_selected_job()

    assert calls == [(12345, 15)]
    assert JobStore(tmp_path).get(job.job_id).status == "stopped"
    assert state.chat[-1].content == f"Stopped job {job.job_id}."
    assert state.tool_log[-1].status == "stopped"
    assert load_persisted_tool_log(tmp_path, session_id=state.active_session_id)[-1].detail == "cmatrix"

def test_tui_runtime_command_stops_background_job(tmp_path, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "mlpcopilot.runtime.jobs.os.killpg",
        lambda process_group, sig: calls.append((process_group, sig)),
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

    result = handle_tui_runtime_command(config, f"/stop {job.job_id}", state=state)

    assert result == f"Stopped job {job.job_id}."
    assert calls == [(12345, 15)]
    assert JobStore(tmp_path).get(job.job_id).status == "stopped"
    assert len(state.tool_log) == 1
    assert state.tool_log[0].name == "exec"
    assert state.tool_log[0].status == "stopped"
    assert state.tool_log[0].detail == "cmatrix"

async def test_tui_ps_lists_foreground_exec_while_running(tmp_path) -> None:
    import shlex
    import sys

    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    command = (
        f"{shlex.quote(sys.executable)} -c "
        f"{shlex.quote('import time; time.sleep(0.5)')}"
    )
    tool = ExecTool(timeout=5, working_dir=str(tmp_path))
    task = asyncio.create_task(tool.execute(command=command))
    try:
        for _ in range(50):
            jobs = JobStore(tmp_path).list_jobs(limit=None)
            if jobs and jobs[0].status == "running":
                break
            await asyncio.sleep(0.02)
        else:
            raise AssertionError("foreground exec job was not recorded as running")

        result = handle_tui_runtime_command(config, "/ps")

        assert result is not None
        assert "Recent jobs:" in result
        assert "running exec" in result
        assert "time.s" in result
    finally:
        if not task.done():
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

def test_tui_runtime_command_logs_missing_background_job_stop(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    state = RuntimeTuiState()

    result = handle_tui_runtime_command(config, "/stop missing_job", state=state)

    assert result == "Job not found: missing_job"
    assert len(state.tool_log) == 1
    assert state.tool_log[0].name == "job"
    assert state.tool_log[0].status == "error"
    assert state.tool_log[0].detail == "missing_job"

def test_job_store_finish_preserves_stopped_status(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "mlpcopilot.runtime.jobs.os.killpg",
        lambda _pg, _sig: None,
        raising=False,
    )
    store = JobStore(tmp_path)
    job = store.record_start(
        kind="exec",
        command="cmatrix",
        pid=os.getpid(),
        process_group=12345,
        cwd=str(tmp_path),
        log_path=tmp_path / "jobs" / "exec_demo.log",
    )

    store.stop(job.job_id)
    finished = store.finish(job.job_id, returncode=-15)

    assert finished is not None
    assert finished.status == "stopped"
    assert finished.returncode == -15

def test_job_store_finish_marks_unstopped_failure(tmp_path) -> None:
    store = JobStore(tmp_path)
    job = store.record_start(
        kind="exec",
        command="train",
        pid=os.getpid(),
        process_group=os.getpid(),
        cwd=str(tmp_path),
        log_path=tmp_path / "jobs" / "exec_demo.log",
    )

    finished = store.finish(job.job_id, returncode=1)

    assert finished is not None
    assert finished.status == "failed"
    assert finished.returncode == 1

def test_tui_input_controller_stops_job_without_queueing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "mlpcopilot.runtime.jobs.os.killpg",
        lambda _pg, _sig: None,
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
    state = RuntimeTuiState(running=True)
    queue = _FakeQueue()
    controller = TuiInputController(config=config, state=state, queue=queue, app_ref={})

    controller.submit(f"/stop {job.job_id}")

    assert queue.items == []
    assert [(message.role, message.content) for message in state.chat] == [
        ("user", f"/stop {job.job_id}"),
        ("system", f"Stopped job {job.job_id}."),
    ]
