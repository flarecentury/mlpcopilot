from mlpcopilot.providers.base import LLMResponse
from mlpcopilot.runtime.workstate import (
    apply_goal_command,
    apply_plan_command,
    apply_project_command,
    format_workstate_context,
    format_workstate_summary_display,
    get_active_project,
    get_goal,
    get_plan,
    refresh_workstate_summary,
)
from mlpcopilot.session.manager import Session


def test_goal_command_sets_shows_and_clears_goal() -> None:
    session = Session(key="tui:test")

    assert apply_goal_command(session, "finish runtime plan support") == (
        "Goal set:\nfinish runtime plan support"
    )
    assert get_goal(session) == "finish runtime plan support"
    assert apply_goal_command(session, "") == "Current goal:\nfinish runtime plan support"
    assert apply_goal_command(session, "clear") == "Goal cleared."
    assert apply_goal_command(session, "") == "Goal: none."


def test_plan_command_manages_checklist_statuses() -> None:
    session = Session(key="tui:test")

    result = apply_plan_command(session, "set [ ] first\n[~] second\n[x] third")
    assert "1. [pending] first" in result
    assert "2. [in_progress] second" in result
    assert "3. [completed] third" in result

    result = apply_plan_command(session, "doing 1")
    assert "1. [in_progress] first" in result
    assert "2. [pending] second" in result

    result = apply_plan_command(session, "done 1")
    assert "1. [completed] first" in result
    assert get_plan(session)[0].status == "completed"


def test_workstate_context_formats_goal_and_plan() -> None:
    session = Session(key="tui:test")
    apply_goal_command(session, "validate DP-GEN iteration")
    apply_plan_command(session, "set inspect logs\nupdate machine file")

    assert format_workstate_context(session) == (
        "Current Goal:\n"
        "validate DP-GEN iteration\n\n"
        "Current Plan:\n"
        "1. [pending] inspect logs\n"
        "2. [pending] update machine file"
    )


def test_workstate_summary_display_uses_two_compact_lines() -> None:
    session = Session(key="tui:test")
    apply_goal_command(session, "完成当前主动学习迭代检查")
    apply_plan_command(session, "add inspect dpdispatcher logs and errors")

    assert format_workstate_summary_display(session) == (
        "goal: 完成当前主动学习迭代检查\n"
        "plan: inspect dpdispatcher logs and errors"
    )


def test_completed_plan_is_not_current_workstate() -> None:
    session = Session(key="tui:test")
    apply_goal_command(session, "finish active learning")
    apply_plan_command(session, "add inspect logs")
    apply_plan_command(session, "done 1")

    assert format_workstate_summary_display(session) == (
        "goal: finish active learning\n"
        "plan: -"
    )
    assert format_workstate_context(session) == (
        "Current Goal:\n"
        "finish active learning"
    )


def test_active_project_pointer_formats_into_runtime_context(tmp_path) -> None:
    from mlpcopilot.runtime.workspace import create_mlp_project, create_mlp_run

    create_mlp_project(tmp_path, name="local", project_id="local_dpgen")
    create_mlp_run(tmp_path, "local_dpgen", run_id="run_local")
    session = Session(key="tui:test")

    result = apply_project_command(session, "set local_dpgen", workspace=tmp_path)
    pointer = get_active_project(session)

    assert pointer is not None
    assert pointer.project_id == "local_dpgen"
    assert pointer.run_id == "run_local"
    assert pointer.backend == "dpgen"
    assert str(tmp_path / "projects" / "local_dpgen" / "runs" / "run_local" / "backend" / "dpgen") in result
    assert format_workstate_context(session) == (
        "[Active MLP Project]\n"
        "project_id: local_dpgen\n"
        "run_id: run_local\n"
        "backend: dpgen\n"
        f"project_path: {tmp_path / 'projects' / 'local_dpgen' / 'runs' / 'run_local' / 'backend' / 'dpgen'}\n"
        f"param_path: {tmp_path / 'projects' / 'local_dpgen' / 'runs' / 'run_local' / 'backend' / 'dpgen' / 'param.json'}\n"
        f"machine_path: {tmp_path / 'projects' / 'local_dpgen' / 'runs' / 'run_local' / 'backend' / 'dpgen' / 'machine.json'}\n"
        "status_source: call MCP tools for live state\n"
        "[/Active MLP Project]"
    )


def test_project_command_clears_active_project() -> None:
    session = Session(key="tui:test")
    apply_project_command(session, "proj_demo run_demo")

    assert "proj_demo" in apply_project_command(session, "")
    assert apply_project_command(session, "clear") == "Active project cleared."
    assert apply_project_command(session, "") == "Active project: none."


async def test_refresh_workstate_summary_uses_provider() -> None:
    session = Session(key="tui:test")
    apply_goal_command(session, "prepare a dataset validation handoff note")
    provider = _FakeSummaryProvider("handoff note")

    result = await refresh_workstate_summary(
        session,
        provider=provider,
        model="test/model",
        target="goal",
    )

    assert result.used_ai is True
    assert result.error == ""
    assert result.summary == "handoff note"
    assert session.metadata["_work_goal_summary"] == "handoff note"
    assert provider.calls[0]["model"] == "test/model"
    assert "max_tokens" not in provider.calls[0]


async def test_refresh_workstate_summary_marks_fallback_without_provider() -> None:
    session = Session(key="tui:test")
    apply_goal_command(session, "finish active learning iteration")

    result = await refresh_workstate_summary(
        session,
        provider=None,
        model="test/model",
        target="goal",
    )

    assert result.used_ai is False
    assert result.error == "provider unavailable"
    assert result.summary == "finish active learning iteration"


async def test_refresh_workstate_summary_retries_empty_response() -> None:
    session = Session(key="tui:test")
    apply_goal_command(session, "prepare a dataset validation handoff note")
    provider = _FakeSummaryProvider(["", "handoff note"])

    result = await refresh_workstate_summary(
        session,
        provider=provider,
        model="test/model",
        target="goal",
    )

    assert result.used_ai is True
    assert result.summary == "handoff note"
    assert len(provider.calls) == 2
    assert "empty visible content" in provider.calls[1]["messages"][0]["content"]


async def test_refresh_workstate_summary_reports_empty_finish_reason() -> None:
    session = Session(key="tui:test")
    apply_goal_command(session, "finish active learning iteration")
    provider = _FakeSummaryProvider(["", ""])

    result = await refresh_workstate_summary(
        session,
        provider=provider,
        model="test/model",
        target="goal",
    )

    assert result.used_ai is False
    assert result.error == "empty response finish=stop"
    assert result.summary == "finish active learning iteration"
    assert len(provider.calls) == 2


async def test_refresh_workstate_summary_reports_reasoning_only_length_response() -> None:
    session = Session(key="tui:test")
    apply_goal_command(session, "prepare validation status summary for handoff")
    provider = _FakeSummaryProvider([
        LLMResponse(content="", finish_reason="length", reasoning_content="thinking"),
        LLMResponse(content="", finish_reason="length", reasoning_content="still reasoning"),
    ])

    result = await refresh_workstate_summary(
        session,
        provider=provider,
        model="test/model",
        target="goal",
    )

    assert result.used_ai is False
    assert result.error == "empty response finish=length reasoning_only"
    assert result.summary == "prepare validation status summary for handoff"
    assert session.metadata["_work_goal_summary"] == "prepare validation status summary for handoff"
    assert len(provider.calls) == 2


class _FakeSummaryProvider:
    def __init__(self, content: str | LLMResponse | list[str | LLMResponse]) -> None:
        self.content = [content] if isinstance(content, (str, LLMResponse)) else list(content)
        self.calls: list[dict] = []

    async def chat_with_retry(self, **kwargs) -> LLMResponse:
        self.calls.append(kwargs)
        response = self.content.pop(0)
        if isinstance(response, LLMResponse):
            return response
        return LLMResponse(content=response)
