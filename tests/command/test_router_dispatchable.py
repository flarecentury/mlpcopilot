"""Tests for CommandRouter.is_dispatchable_command and mid-turn command interception."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from mlpcopilot.command.builtin import register_builtin_commands
from mlpcopilot.command.router import CommandContext, CommandRouter
from mlpcopilot.providers.base import LLMResponse


class TestIsDispatchableCommand:
    """Unit tests for the is_dispatchable_command() predicate."""

    @pytest.fixture()
    def router(self) -> CommandRouter:
        r = CommandRouter()
        register_builtin_commands(r)
        return r

    def test_exact_commands_match(self, router: CommandRouter) -> None:
        assert router.is_dispatchable_command("/new")
        assert router.is_dispatchable_command("/help")
        assert router.is_dispatchable_command("/dream")
        assert router.is_dispatchable_command("/dream-log")
        assert router.is_dispatchable_command("/dream-restore")
        assert router.is_dispatchable_command("/dream_log")
        assert router.is_dispatchable_command("/dream_restore")
        assert router.is_dispatchable_command("/model")
        assert router.is_dispatchable_command("/goal")
        assert router.is_dispatchable_command("/plan")
        assert router.is_dispatchable_command("/project")
        assert router.is_dispatchable_command("/memory-audit")
        assert router.is_dispatchable_command("/memory_audit")
        assert router.is_dispatchable_command("/approvals")
        assert router.is_dispatchable_command("/runs")

    def test_prefix_commands_match(self, router: CommandRouter) -> None:
        assert router.is_dispatchable_command("/dream-log abc123")
        assert router.is_dispatchable_command("/dream-restore def456")
        assert router.is_dispatchable_command("/model test/model")
        assert router.is_dispatchable_command("/goal finish the task")
        assert router.is_dispatchable_command("/plan add inspect logs")
        assert router.is_dispatchable_command("/project set local_dpgen run_local")
        assert not router.is_dispatchable_command("/memory-audit extra")
        assert router.is_dispatchable_command("/approve apr_123")
        assert router.is_dispatchable_command("/reject apr_123")
        assert router.is_dispatchable_command("/changes apr_123")
        assert router.is_dispatchable_command("/artifacts run_123")

    def test_priority_commands_not_matched(self, router: CommandRouter) -> None:
        # Priority commands are NOT in the dispatchable tiers — they are
        # handled by is_priority() separately.
        assert not router.is_dispatchable_command("/stop")
        assert not router.is_dispatchable_command("/restart")

    def test_regular_text_not_matched(self, router: CommandRouter) -> None:
        assert not router.is_dispatchable_command("hello")
        assert not router.is_dispatchable_command("what is 2+2?")
        assert not router.is_dispatchable_command("")

    def test_case_insensitive(self, router: CommandRouter) -> None:
        assert router.is_dispatchable_command("/NEW")
        assert router.is_dispatchable_command("/Help")

    def test_strips_whitespace(self, router: CommandRouter) -> None:
        assert router.is_dispatchable_command("  /new  ")

    def test_unknown_slash_command_not_matched(self, router: CommandRouter) -> None:
        assert not router.is_dispatchable_command("/unknown")
        assert not router.is_dispatchable_command("/foo bar")


class TestMidTurnCommandDispatchedDirectly:
    """Verify that commands matching is_dispatchable_command() are dispatched
    correctly when session=None (the mid-turn path)."""

    @pytest.fixture()
    def router(self) -> CommandRouter:
        r = CommandRouter()
        register_builtin_commands(r)
        return r

    @pytest.fixture()
    def fake_loop(self) -> MagicMock:
        loop = MagicMock()
        loop.sessions = MagicMock()
        loop.sessions.get_or_create = MagicMock(return_value=MagicMock(
            messages=[], last_consolidated=0, clear=MagicMock(),
        ))
        loop.sessions.save = MagicMock()
        loop.sessions.invalidate = MagicMock()
        loop._schedule_background = MagicMock()
        loop._cancel_active_tasks = AsyncMock(return_value=0)
        return loop

    @pytest.fixture()
    def fake_msg(self) -> MagicMock:
        msg = MagicMock()
        msg.channel = "test"
        msg.chat_id = "chat1"
        msg.content = "/new"
        msg.metadata = {}
        return msg

    @pytest.mark.asyncio
    async def test_new_dispatched_with_session_none(
        self, router: CommandRouter, fake_loop: MagicMock, fake_msg: MagicMock,
    ) -> None:
        """cmd_new works when session=None (mid-turn dispatch path)."""
        ctx = CommandContext(
            msg=fake_msg, session=None,
            key="test:chat1", raw="/new", loop=fake_loop,
        )
        result = await router.dispatch(ctx)
        assert result is not None
        assert "New session" in result.content
        fake_loop.sessions.get_or_create.assert_called_once_with("test:chat1")

    @pytest.mark.asyncio
    async def test_help_dispatched_with_session_none(
        self, router: CommandRouter, fake_loop: MagicMock, fake_msg: MagicMock,
    ) -> None:
        ctx = CommandContext(
            msg=fake_msg, session=None,
            key="test:chat1", raw="/help", loop=fake_loop,
        )
        result = await router.dispatch(ctx)
        assert result is not None

    @pytest.mark.asyncio
    async def test_prefix_command_args_populated(self, router: CommandRouter) -> None:
        """Prefix commands have args populated correctly in mid-turn path."""
        # Use a custom prefix handler to avoid needing full mock setup.
        custom = CommandRouter()
        captured_args = []

        async def fake_handler(ctx: CommandContext) -> None:
            captured_args.append(ctx.args)
            return None

        custom.prefix("/test ", fake_handler)

        ctx = CommandContext(
            msg=MagicMock(channel="test", chat_id="c1", metadata={}),
            session=None, key="test:c1", raw="/test hello world", loop=MagicMock(),
        )
        await custom.dispatch(ctx)
        assert captured_args == ["hello world"]

    @pytest.mark.asyncio
    async def test_model_command_switches_runtime_model(self, router: CommandRouter, fake_loop: MagicMock, fake_msg: MagicMock) -> None:
        fake_msg.content = "/model test/model"
        fake_loop.model = "old/model"
        fake_loop.switch_runtime_model = MagicMock(return_value="Model switched: old/model -> test/model")
        ctx = CommandContext(
            msg=fake_msg,
            session=None,
            key="test:chat1",
            raw="/model test/model",
            loop=fake_loop,
        )

        result = await router.dispatch(ctx)

        assert result is not None
        assert result.content == "Model switched: old/model -> test/model"
        fake_loop.switch_runtime_model.assert_called_once_with("test/model")

    @pytest.mark.asyncio
    async def test_goal_and_plan_commands_persist_session_metadata(self, router: CommandRouter, fake_msg: MagicMock, tmp_path) -> None:
        from mlpcopilot.session.manager import SessionManager

        sessions = SessionManager(tmp_path)
        fake_loop = MagicMock()
        fake_loop.sessions = sessions
        fake_loop.provider = _FakeSummaryProvider(["active iter", "inspect logs"])
        fake_loop.model = "test/model"
        scheduled = []
        fake_loop._schedule_background = scheduled.append

        goal = await router.dispatch(CommandContext(
            msg=fake_msg,
            session=None,
            key="test:chat1",
            raw="/goal finish active learning iteration",
            loop=fake_loop,
        ))
        plan = await router.dispatch(CommandContext(
            msg=fake_msg,
            session=None,
            key="test:chat1",
            raw="/plan add inspect dpdispatcher logs",
            loop=fake_loop,
        ))

        session = sessions.get_or_create("test:chat1")
        assert goal is not None
        assert "Goal set" in goal.content
        assert "Summary: AI refresh running in background." in goal.content
        assert plan is not None
        assert "inspect dpdispatcher logs" in plan.content
        assert "Summary: AI refresh running in background." in plan.content
        assert session.metadata["_work_goal"] == "finish active learning iteration"
        assert session.metadata["_work_plan"][0]["step"] == "inspect dpdispatcher logs"
        assert len(scheduled) == 2
        await scheduled[0]
        await scheduled[1]
        assert session.metadata["_work_goal_summary"] == "active iter"
        assert session.metadata["_work_plan_summary"] == "inspect logs"

    @pytest.mark.asyncio
    async def test_project_command_persists_active_project_pointer(self, router: CommandRouter, fake_msg: MagicMock, tmp_path) -> None:
        from mlpcopilot.runtime.workspace import create_mlp_project, create_mlp_run
        from mlpcopilot.session.manager import SessionManager

        create_mlp_project(tmp_path, name="local", project_id="local_dpgen")
        create_mlp_run(tmp_path, "local_dpgen", run_id="run_local")
        sessions = SessionManager(tmp_path)
        fake_loop = MagicMock()
        fake_loop.workspace = tmp_path
        fake_loop.sessions = sessions

        result = await router.dispatch(CommandContext(
            msg=fake_msg,
            session=None,
            key="test:chat1",
            raw="/project set local_dpgen",
            loop=fake_loop,
        ))

        session = sessions.get_or_create("test:chat1")
        assert result is not None
        assert "Active project set" in result.content
        assert session.metadata["_active_mlp_project"]["project_id"] == "local_dpgen"
        assert session.metadata["_active_mlp_project"]["run_id"] == "run_local"

    @pytest.mark.asyncio
    async def test_memory_audit_command_reports_stale_memory(self, router: CommandRouter, fake_msg: MagicMock, tmp_path) -> None:
        from mlpcopilot.session.manager import SessionManager

        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        (memory_dir / "MEMORY.md").write_text(
            "- Current status: iter.000021 stage0 make_train.\n",
            encoding="utf-8",
        )
        fake_loop = MagicMock()
        fake_loop.workspace = tmp_path
        fake_loop.sessions = SessionManager(tmp_path)

        result = await router.dispatch(CommandContext(
            msg=fake_msg,
            session=None,
            key="test:chat1",
            raw="/memory-audit",
            loop=fake_loop,
        ))

        assert result is not None
        assert "Memory audit" in result.content
        assert "dpgen-iteration" in result.content

    @pytest.mark.asyncio
    async def test_non_command_returns_none(
        self, router: CommandRouter, fake_loop: MagicMock, fake_msg: MagicMock,
    ) -> None:
        """Regular text returns None from dispatch (not a command)."""
        ctx = CommandContext(
            msg=fake_msg, session=None,
            key="test:chat1", raw="hello world", loop=fake_loop,
        )
        result = await router.dispatch(ctx)
        assert result is None


class _FakeSummaryProvider:
    def __init__(self, summaries: list[str]) -> None:
        self.summaries = summaries

    async def chat_with_retry(self, **_kwargs) -> LLMResponse:
        return LLMResponse(content=self.summaries.pop(0))
