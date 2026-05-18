import pytest

from mlpcopilot.agent.tools.session_context import bind_session_key, reset_session_key
from mlpcopilot.agent.tools.workstate import WorkStateTool
from mlpcopilot.runtime.workstate import (
    apply_goal_command,
    apply_plan_command,
    format_workstate_summary_display,
    get_active_project,
)
from mlpcopilot.session.manager import SessionManager


@pytest.mark.asyncio
async def test_workstate_tool_marks_plan_item_completed(tmp_path) -> None:
    sessions = SessionManager(tmp_path)
    session = sessions.get_or_create("tui:default")
    apply_goal_command(session, "finish active learning")
    apply_plan_command(session, "add inspect logs")
    sessions.save(session)
    tool = WorkStateTool(sessions)
    token = bind_session_key("tui:default")
    try:
        result = await tool.execute(
            action="update_plan_status",
            index=1,
            status="completed",
        )
    finally:
        reset_session_key(token)

    updated = sessions.get_or_create("tui:default")
    assert "1. [completed] inspect logs" in result
    assert updated.metadata["_work_plan"][0]["status"] == "completed"
    assert format_workstate_summary_display(updated) == (
        "goal: finish active learning\n"
        "plan: -"
    )


@pytest.mark.asyncio
async def test_workstate_tool_clears_goal(tmp_path) -> None:
    sessions = SessionManager(tmp_path)
    session = sessions.get_or_create("tui:default")
    apply_goal_command(session, "temporary goal")
    sessions.save(session)
    tool = WorkStateTool(sessions)
    token = bind_session_key("tui:default")
    try:
        result = await tool.execute(action="clear_goal")
    finally:
        reset_session_key(token)

    updated = sessions.get_or_create("tui:default")
    assert "Goal cleared." in result
    assert "_work_goal" not in updated.metadata
    assert format_workstate_summary_display(updated).startswith("goal: -")


@pytest.mark.asyncio
async def test_workstate_tool_sets_active_project_pointer(tmp_path) -> None:
    sessions = SessionManager(tmp_path)
    sessions.get_or_create("tui:default")
    tool = WorkStateTool(sessions)
    token = bind_session_key("tui:default")
    try:
        result = await tool.execute(
            action="set_active_project",
            project_id="local_dpgen",
            run_id="run_local",
            backend="dpgen",
            project_path="/tmp/backend/dpgen",
        )
    finally:
        reset_session_key(token)

    updated = sessions.get_or_create("tui:default")
    pointer = get_active_project(updated)
    assert pointer is not None
    assert pointer.project_id == "local_dpgen"
    assert pointer.run_id == "run_local"
    assert pointer.backend == "dpgen"
    assert "Active project set" in result
    assert "[Active MLP Project]" in result
