"""Built-in slash command handlers."""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import suppress
from pathlib import Path

from mlpcopilot import __version__
from mlpcopilot.bus.events import OutboundMessage
from mlpcopilot.command.registry import format_command_help, list_commands
from mlpcopilot.command.router import CommandContext, CommandRouter
from mlpcopilot.runtime.workstate import (
    SummaryRefreshResult,
    apply_goal_command,
    apply_plan_command,
    apply_project_command,
    refresh_workstate_summary_for_session,
)
from mlpcopilot.utils.helpers import build_status_content
from mlpcopilot.utils.restart import set_restart_notice_to_env


async def cmd_stop(ctx: CommandContext) -> OutboundMessage:
    """Cancel all active tasks and subagents for the session."""
    loop = ctx.loop
    msg = ctx.msg
    total = await loop._cancel_active_tasks(msg.session_key)
    content = f"Stopped {total} task(s)." if total else "No active task to stop."
    return OutboundMessage(
        channel=msg.channel, chat_id=msg.chat_id, content=content,
        metadata=dict(msg.metadata or {})
    )


async def cmd_restart(ctx: CommandContext) -> OutboundMessage:
    """Restart the process in-place via os.execv."""
    msg = ctx.msg
    set_restart_notice_to_env(
        channel=msg.channel,
        chat_id=msg.chat_id,
        metadata=dict(msg.metadata or {}),
    )

    async def _do_restart():
        await asyncio.sleep(1)
        os.execv(sys.executable, [sys.executable, "-m", "mlpcopilot"] + sys.argv[1:])

    asyncio.create_task(_do_restart())
    return OutboundMessage(
        channel=msg.channel, chat_id=msg.chat_id, content="Restarting...",
        metadata=dict(msg.metadata or {})
    )


async def cmd_status(ctx: CommandContext) -> OutboundMessage:
    """Build an outbound status message for a session."""
    loop = ctx.loop
    session = ctx.session or loop.sessions.get_or_create(ctx.key)
    ctx_est = 0
    with suppress(Exception):
        ctx_est, _ = loop.consolidator.estimate_session_prompt_tokens(session)
    if ctx_est <= 0:
        ctx_est = loop._last_usage.get("prompt_tokens", 0)

    # Fetch web search provider usage (best-effort, never blocks the response)
    search_usage_text: str | None = None
    # Never let usage fetch break /status
    with suppress(Exception):
        from mlpcopilot.utils.searchusage import fetch_search_usage
        web_cfg = getattr(loop, "web_config", None)
        search_cfg = getattr(web_cfg, "search", None) if web_cfg else None
        if search_cfg is not None:
            provider = getattr(search_cfg, "provider", "duckduckgo")
            api_key = getattr(search_cfg, "api_key", "") or None
            usage = await fetch_search_usage(provider=provider, api_key=api_key)
            search_usage_text = usage.format()
    active_tasks = loop._active_tasks.get(ctx.key, [])
    task_count = sum(1 for t in active_tasks if not t.done())
    with suppress(Exception):
        task_count += loop.subagents.get_running_count_by_session(ctx.key)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=build_status_content(
            version=__version__, model=loop.model,
            start_time=loop._start_time, last_usage=loop._last_usage,
            context_window_tokens=loop.context_window_tokens,
            session_msg_count=len(session.get_history(max_messages=0)),
            context_tokens_estimate=ctx_est,
            search_usage_text=search_usage_text,
            active_task_count=task_count,
            max_completion_tokens=getattr(
                getattr(loop.provider, "generation", None), "max_tokens", 8192
            ),
        ),
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


async def cmd_new(ctx: CommandContext) -> OutboundMessage:
    """Stop active task and start a fresh session."""
    loop = ctx.loop
    await loop._cancel_active_tasks(ctx.key)
    session = ctx.session or loop.sessions.get_or_create(ctx.key)
    snapshot = session.messages[session.last_consolidated:]
    session.clear()
    loop.sessions.save(session)
    loop.sessions.invalidate(session.key)
    if snapshot:
        loop._schedule_background(loop.consolidator.archive(snapshot))
    return OutboundMessage(
        channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
        content="New session started.",
        metadata=dict(ctx.msg.metadata or {})
    )


async def cmd_dream(ctx: CommandContext) -> OutboundMessage:
    """Manually trigger a Dream consolidation run."""
    import time

    loop = ctx.loop
    msg = ctx.msg

    async def _run_dream():
        t0 = time.monotonic()
        try:
            did_work = await loop.dream.run()
            elapsed = time.monotonic() - t0
            if did_work:
                content = f"Dream completed in {elapsed:.1f}s."
            elif getattr(loop.dream, "last_status", "") == "approval_pending":
                content = "Dream: approval required. Review the pending approval, then run /dream again."
            else:
                content = "Dream: nothing to process."
        except Exception as e:
            elapsed = time.monotonic() - t0
            content = f"Dream failed after {elapsed:.1f}s: {e}"
        await loop.bus.publish_outbound(OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id, content=content,
        ))

    asyncio.create_task(_run_dream())
    return OutboundMessage(
        channel=msg.channel, chat_id=msg.chat_id, content="Dreaming...",
    )


def _extract_changed_files(diff: str) -> list[str]:
    """Extract changed file paths from a unified diff."""
    files: list[str] = []
    seen: set[str] = set()
    for line in diff.splitlines():
        if not line.startswith("diff --git "):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        path = parts[3]
        if path.startswith("b/"):
            path = path[2:]
        if path in seen:
            continue
        seen.add(path)
        files.append(path)
    return files


def _format_changed_files(diff: str) -> str:
    files = _extract_changed_files(diff)
    if not files:
        return "No tracked memory files changed."
    return ", ".join(f"`{path}`" for path in files)


def _format_dream_log_content(commit, diff: str, *, requested_sha: str | None = None) -> str:
    files_line = _format_changed_files(diff)
    lines = [
        "## Dream Update",
        "",
        "Here is the selected Dream memory change." if requested_sha else "Here is the latest Dream memory change.",
        "",
        f"- Commit: `{commit.sha}`",
        f"- Time: {commit.timestamp}",
        f"- Changed files: {files_line}",
    ]
    if diff:
        lines.extend([
            "",
            f"Use `/dream-restore {commit.sha}` to undo this change.",
            "",
            "```diff",
            diff.rstrip(),
            "```",
        ])
    else:
        lines.extend([
            "",
            "Dream recorded this version, but there is no file diff to display.",
        ])
    return "\n".join(lines)


def _format_dream_restore_list(commits: list) -> str:
    lines = [
        "## Dream Restore",
        "",
        "Choose a Dream memory version to restore. Latest first:",
        "",
    ]
    for c in commits:
        lines.append(f"- `{c.sha}` {c.timestamp} - {c.message.splitlines()[0]}")
    lines.extend([
        "",
        "Preview a version with `/dream-log <sha>` before restoring it.",
        "Restore a version with `/dream-restore <sha>`.",
    ])
    return "\n".join(lines)


async def cmd_dream_log(ctx: CommandContext) -> OutboundMessage:
    """Show what the last Dream changed.

    Default: diff of the latest commit (HEAD~1 vs HEAD).
    With /dream-log <sha>: diff of that specific commit.
    """
    store = ctx.loop.consolidator.store
    git = store.git

    if not git.is_initialized():
        if store.get_last_dream_cursor() == 0:
            msg = "Dream has not run yet. Run `/dream`, or wait for the next scheduled Dream cycle."
        else:
            msg = "Dream history is not available because memory versioning is not initialized."
        return OutboundMessage(
            channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
            content=msg, metadata={"render_as": "text"},
        )

    args = ctx.args.strip()

    if args:
        # Show diff of a specific commit
        sha = args.split()[0]
        result = git.show_commit_diff(sha)
        if not result:
            content = (
                f"Couldn't find Dream change `{sha}`.\n\n"
                "Use `/dream-restore` to list recent versions, "
                "or `/dream-log` to inspect the latest one."
            )
        else:
            commit, diff = result
            content = _format_dream_log_content(commit, diff, requested_sha=sha)
    else:
        # Default: show the latest commit's diff
        commits = git.log(max_entries=1)
        result = git.show_commit_diff(commits[0].sha) if commits else None
        if result:
            commit, diff = result
            content = _format_dream_log_content(commit, diff)
        else:
            content = "Dream memory has no saved versions yet."

    return OutboundMessage(
        channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
        content=content, metadata={"render_as": "text"},
    )


async def cmd_dream_restore(ctx: CommandContext) -> OutboundMessage:
    """Restore memory files from a previous dream commit.

    Usage:
        /dream-restore          — list recent commits
        /dream-restore <sha>    — revert a specific commit
    """
    store = ctx.loop.consolidator.store
    git = store.git
    if not git.is_initialized():
        return OutboundMessage(
            channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
            content="Dream history is not available because memory versioning is not initialized.",
        )

    args = ctx.args.strip()
    if not args:
        # Show recent commits for the user to pick
        commits = git.log(max_entries=10)
        if not commits:
            content = "Dream memory has no saved versions to restore yet."
        else:
            content = _format_dream_restore_list(commits)
    else:
        sha = args.split()[0]
        result = git.show_commit_diff(sha)
        changed_files = _format_changed_files(result[1]) if result else "the tracked memory files"
        new_sha = git.revert(sha)
        if new_sha:
            content = (
                f"Restored Dream memory to the state before `{sha}`.\n\n"
                f"- New safety commit: `{new_sha}`\n"
                f"- Restored files: {changed_files}\n\n"
                f"Use `/dream-log {new_sha}` to inspect the restore diff."
            )
        else:
            content = (
                f"Couldn't restore Dream change `{sha}`.\n\n"
                "It may not exist, or it may be the first saved version with no earlier state to restore."
            )
    return OutboundMessage(
        channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
        content=content, metadata={"render_as": "text"},
    )


_HISTORY_DEFAULT_COUNT = 10
_HISTORY_MAX_COUNT = 50
_HISTORY_MAX_CONTENT_CHARS = 200


def _format_history_message(msg: dict) -> str | None:
    """Format a single history message for display. Returns None to skip."""
    role = msg.get("role")
    if role not in ("user", "assistant"):
        return None
    content = msg.get("content") or ""
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        content = " ".join(parts)
    content = str(content).strip()
    if not content:
        return None
    if len(content) > _HISTORY_MAX_CONTENT_CHARS:
        content = content[:_HISTORY_MAX_CONTENT_CHARS] + "…"
    label = "👤 You" if role == "user" else "🤖 Bot"
    return f"{label}: {content}"


def _split_id_reason(args: str, *, usage: str) -> tuple[str | None, str | None, str | None]:
    parts = args.strip().split(maxsplit=1)
    if not parts:
        return None, None, usage
    return parts[0], parts[1] if len(parts) > 1 else None, None


def _approval_manager(ctx: CommandContext):
    from mlpcopilot.runtime.approval import ApprovalManager

    return ApprovalManager(ctx.loop.workspace)


def _artifact_index(ctx: CommandContext):
    from mlpcopilot.runtime.artifacts import ArtifactIndex

    return ArtifactIndex(ctx.loop.workspace)


def _format_approval_line(record) -> str:
    title = record.title.strip() or record.action_type
    suffix = f" run={record.run_id}" if record.run_id else ""
    return f"- {record.approval_id} [{record.status}] {title}{suffix}"


async def cmd_approvals(ctx: CommandContext) -> OutboundMessage:
    """List pending approvals, or recent decisions with /approvals decisions."""
    manager = _approval_manager(ctx)
    mode = ctx.args.strip().lower()
    if mode in {"decisions", "decision", "all"}:
        records = manager.list_decisions()
        title = "Recent approval decisions"
    else:
        records = manager.list_pending()
        title = "Pending approvals"

    if not records:
        content = f"{title}: none."
    else:
        lines = [f"{title}:"]
        for record in records[-20:]:
            lines.append(_format_approval_line(record))
        content = "\n".join(lines)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=content,
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


async def _approval_decision_command(ctx: CommandContext, action: str) -> OutboundMessage:
    usage = f"Usage: /{action} <approval_id> [reason]"
    approval_id, reason, error = _split_id_reason(ctx.args, usage=usage)
    if error or not approval_id:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=error or usage,
            metadata=dict(ctx.msg.metadata or {}),
        )

    manager = _approval_manager(ctx)
    try:
        if action == "approve":
            record, changed = manager.approve_or_get(
                approval_id,
                decided_by=ctx.msg.sender_id,
                reason=reason,
            )
        elif action == "reject":
            record = manager.reject(approval_id, decided_by=ctx.msg.sender_id, reason=reason)
            changed = True
        else:
            record = manager.needs_changes(
                approval_id,
                decided_by=ctx.msg.sender_id,
                reason=reason,
            )
            changed = True
    except (KeyError, ValueError) as exc:
        content = str(exc)
    else:
        verb = "marked" if changed else "already"
        content = f"Approval {record.approval_id} {verb} {record.status}."
        if action == "approve":
            from mlpcopilot.runtime.approval import resume_approved_action

            resumed = await resume_approved_action(ctx.loop, record)
            if resumed:
                content = f"{content}\n\n{resumed}"
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=content,
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


async def cmd_approve(ctx: CommandContext) -> OutboundMessage:
    return await _approval_decision_command(ctx, "approve")


async def cmd_reject(ctx: CommandContext) -> OutboundMessage:
    return await _approval_decision_command(ctx, "reject")


async def cmd_changes(ctx: CommandContext) -> OutboundMessage:
    return await _approval_decision_command(ctx, "changes")


def _format_run_line(manifest) -> str:
    source = f" source={manifest.source}" if manifest.source else ""
    return f"- {manifest.run_id} {manifest.created_at}{source}"


async def cmd_runs(ctx: CommandContext) -> OutboundMessage:
    """List recent run manifests."""
    runs = _artifact_index(ctx).list_runs()
    if not runs:
        content = "Runs: none."
    else:
        lines = ["Recent runs:"]
        for manifest in runs[:20]:
            lines.append(_format_run_line(manifest))
        content = "\n".join(lines)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=content,
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


async def cmd_artifacts(ctx: CommandContext) -> OutboundMessage:
    """Show artifact references for a run manifest."""
    run_id = ctx.args.strip()
    if not run_id:
        content = "Usage: /artifacts <run_id>"
    else:
        try:
            manifest = _artifact_index(ctx).load(run_id)
        except (FileNotFoundError, ValueError) as exc:
            content = str(exc)
        else:
            lines = [f"Artifacts for {manifest.run_id}:"]
            if manifest.artifacts:
                for item in manifest.artifacts:
                    lines.append(f"- {item}")
            else:
                lines.append("- none")
            if manifest.outputs:
                lines.append("Outputs:")
                for item in manifest.outputs:
                    lines.append(f"- {item}")
            content = "\n".join(lines)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=content,
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


async def cmd_history(ctx: CommandContext) -> OutboundMessage:
    """Show the last N messages of the current session (default 10, max 50).

    Usage: /history [count]
    """
    count = _HISTORY_DEFAULT_COUNT
    if ctx.args.strip():
        try:
            count = max(1, min(int(ctx.args.strip()), _HISTORY_MAX_COUNT))
        except ValueError:
            return OutboundMessage(
                channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
                content="Usage: /history [count] — e.g. /history 5 (default: 10, max: 50)",
                metadata=dict(ctx.msg.metadata or {}),
            )

    session = ctx.session or ctx.loop.sessions.get_or_create(ctx.key)
    history = session.get_history(max_messages=0)
    visible = [_format_history_message(m) for m in history]
    visible = [m for m in visible if m is not None]
    recent = visible[-count:]

    if not recent:
        return OutboundMessage(
            channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
            content="No conversation history yet.",
            metadata=dict(ctx.msg.metadata or {}),
        )

    header = f"Last {len(recent)} message(s):\n"
    return OutboundMessage(
        channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
        content=header + "\n".join(recent),
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


def _format_model_status(ctx: CommandContext) -> str:
    model = getattr(ctx.loop, "model", None) or "unknown"
    return f"Current model: {model}\nSwitch with /model <model>."


async def cmd_model(ctx: CommandContext) -> OutboundMessage:
    """Show or switch the active runtime model."""
    requested = ctx.args.strip()
    content = _format_model_status(ctx)
    if requested:
        apply_model = getattr(ctx.loop, "switch_runtime_model", None)
        if apply_model is None:
            content = "Error: this runtime cannot switch models."
        else:
            try:
                content = apply_model(requested)
            except Exception as exc:
                content = f"Error: {exc}"
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=content,
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


async def cmd_goal(ctx: CommandContext) -> OutboundMessage:
    """Show or set the current session goal."""
    session = ctx.session or ctx.loop.sessions.get_or_create(ctx.key)
    content = apply_goal_command(session, ctx.args)
    if ctx.args.strip():
        _schedule_workstate_summary_refresh(ctx, "goal")
    ctx.loop.sessions.save(session)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=_append_summary_line(content, scheduled=bool(ctx.args.strip())),
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


async def cmd_plan(ctx: CommandContext) -> OutboundMessage:
    """Show or update the current session plan."""
    session = ctx.session or ctx.loop.sessions.get_or_create(ctx.key)
    content = apply_plan_command(session, ctx.args)
    if ctx.args.strip():
        _schedule_workstate_summary_refresh(ctx, "plan")
    ctx.loop.sessions.save(session)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=_append_summary_line(content, scheduled=bool(ctx.args.strip())),
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


async def cmd_project(ctx: CommandContext) -> OutboundMessage:
    """Show or set the current active MLP project/run pointer."""
    session = ctx.session or ctx.loop.sessions.get_or_create(ctx.key)
    workspace = getattr(ctx.loop, "workspace", None)
    try:
        content = apply_project_command(session, ctx.args, workspace=workspace)
    except Exception as exc:
        content = f"Error: {exc}"
    ctx.loop.sessions.save(session)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=content,
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


async def cmd_memory_audit(ctx: CommandContext) -> OutboundMessage:
    """Scan durable memory for likely stale runtime facts."""
    from mlpcopilot.runtime.memory_audit import format_memory_audit_report

    workspace = Path(getattr(ctx.loop, "workspace", "."))
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=format_memory_audit_report(workspace),
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


def _schedule_workstate_summary_refresh(
    ctx: CommandContext,
    target: str,
) -> None:
    coro = refresh_workstate_summary_for_session(
        ctx.loop.sessions,
        ctx.key,
        provider=getattr(ctx.loop, "provider", None),
        model=getattr(ctx.loop, "model", None),
        target=target,  # type: ignore[arg-type]
    )
    scheduler = getattr(ctx.loop, "_schedule_background", None)
    if callable(scheduler):
        scheduler(coro)
    else:
        asyncio.create_task(coro)


def _append_summary_line(
    content: str,
    summary: SummaryRefreshResult | None = None,
    *,
    scheduled: bool = False,
) -> str:
    if summary is None or not summary.summary:
        if scheduled:
            return f"{content}\nSummary: AI refresh running in background."
        return content
    if summary.used_ai:
        return f"{content}\nSummary (ai): {summary.summary}"
    if summary.error:
        return f"{content}\nSummary (fallback: {summary.error}): {summary.summary}"
    return f"{content}\nSummary (fallback): {summary.summary}"


async def cmd_help(ctx: CommandContext) -> OutboundMessage:
    """Return available slash commands."""
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=build_help_text(getattr(ctx.loop, "runtime_config", None), surface="gateway"),
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


def build_help_text(config: object | None = None, *, surface: str = "gateway") -> str:
    """Build canonical help text shared across channels."""
    return format_command_help(surface=surface, config=config, title="🐈 mlpcopilot commands:")


def register_builtin_commands(router: CommandRouter) -> None:
    """Register the default set of slash commands."""
    handlers = {
        "/approve": cmd_approve,
        "/approvals": cmd_approvals,
        "/artifacts": cmd_artifacts,
        "/changes": cmd_changes,
        "/dream": cmd_dream,
        "/dream-log": cmd_dream_log,
        "/dream-restore": cmd_dream_restore,
        "/help": cmd_help,
        "/history": cmd_history,
        "/memory-audit": cmd_memory_audit,
        "/goal": cmd_goal,
        "/model": cmd_model,
        "/new": cmd_new,
        "/plan": cmd_plan,
        "/project": cmd_project,
        "/reject": cmd_reject,
        "/restart": cmd_restart,
        "/runs": cmd_runs,
        "/status": cmd_status,
        "/stop": cmd_stop,
    }
    for command in list_commands(surface="gateway", include_hidden=True):
        handler = handlers.get(command.name)
        if handler is None:
            continue
        names = (command.name, *command.aliases)
        for name in names:
            if command.priority:
                router.priority(name, handler)
            elif command.takes_arg:
                router.exact(name, handler)
                router.prefix(f"{name} ", handler)
            else:
                router.exact(name, handler)
