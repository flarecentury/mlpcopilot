"""Session-scoped goal and plan state for runtime surfaces."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from mlpcopilot.utils.helpers import strip_think

PlanStatus = Literal["pending", "in_progress", "completed"]

GOAL_METADATA_KEY = "_work_goal"
PLAN_METADATA_KEY = "_work_plan"
GOAL_SUMMARY_METADATA_KEY = "_work_goal_summary"
PLAN_SUMMARY_METADATA_KEY = "_work_plan_summary"
ACTIVE_PROJECT_METADATA_KEY = "_active_mlp_project"
_VALID_STATUSES: set[str] = {"pending", "in_progress", "completed"}
_CJK_RE = re.compile(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]")


@dataclass(frozen=True, slots=True)
class PlanItem:
    step: str
    status: PlanStatus = "pending"

    def to_dict(self) -> dict[str, str]:
        return {"step": self.step, "status": self.status}


@dataclass(frozen=True, slots=True)
class SummaryRefreshResult:
    summary: str
    used_ai: bool = False
    error: str = ""


@dataclass(frozen=True, slots=True)
class ActiveProjectPointer:
    project_id: str
    run_id: str = ""
    backend: str = ""
    project_path: str = ""
    param_path: str = ""
    machine_path: str = ""

    def to_dict(self) -> dict[str, str]:
        payload = {
            "project_id": self.project_id,
            "run_id": self.run_id,
            "backend": self.backend,
            "project_path": self.project_path,
            "param_path": self.param_path,
            "machine_path": self.machine_path,
        }
        return {key: value for key, value in payload.items() if value}


def get_goal(session: Any) -> str:
    value = getattr(session, "metadata", {}).get(GOAL_METADATA_KEY)
    return value.strip() if isinstance(value, str) else ""


def set_goal(session: Any, goal: str) -> str:
    goal = goal.strip()
    if goal:
        session.metadata[GOAL_METADATA_KEY] = goal
        session.metadata[GOAL_SUMMARY_METADATA_KEY] = compact_workstate_summary(goal)
    else:
        session.metadata.pop(GOAL_METADATA_KEY, None)
        session.metadata.pop(GOAL_SUMMARY_METADATA_KEY, None)
    return goal


def get_plan(session: Any) -> list[PlanItem]:
    raw_plan = getattr(session, "metadata", {}).get(PLAN_METADATA_KEY)
    if not isinstance(raw_plan, list):
        return []
    plan: list[PlanItem] = []
    for item in raw_plan:
        if not isinstance(item, dict):
            continue
        step = str(item.get("step") or "").strip()
        status = str(item.get("status") or "pending").strip()
        if not step:
            continue
        if status not in _VALID_STATUSES:
            status = "pending"
        plan.append(PlanItem(step=step, status=status))  # type: ignore[arg-type]
    return plan


def set_plan(session: Any, plan: list[PlanItem]) -> list[PlanItem]:
    normalized = _normalize_plan(plan)
    if normalized:
        session.metadata[PLAN_METADATA_KEY] = [item.to_dict() for item in normalized]
    else:
        session.metadata.pop(PLAN_METADATA_KEY, None)
    return normalized


def clear_plan(session: Any) -> None:
    session.metadata.pop(PLAN_METADATA_KEY, None)
    session.metadata.pop(PLAN_SUMMARY_METADATA_KEY, None)


def get_active_project(session: Any) -> ActiveProjectPointer | None:
    raw = getattr(session, "metadata", {}).get(ACTIVE_PROJECT_METADATA_KEY)
    if not isinstance(raw, dict):
        return None
    project_id = str(raw.get("project_id") or "").strip()
    if not project_id:
        return None
    return ActiveProjectPointer(
        project_id=project_id,
        run_id=str(raw.get("run_id") or "").strip(),
        backend=str(raw.get("backend") or "").strip(),
        project_path=str(raw.get("project_path") or "").strip(),
        param_path=str(raw.get("param_path") or "").strip(),
        machine_path=str(raw.get("machine_path") or "").strip(),
    )


def set_active_project(
    session: Any,
    *,
    project_id: str,
    run_id: str = "",
    backend: str = "",
    project_path: str = "",
    param_path: str = "",
    machine_path: str = "",
) -> ActiveProjectPointer:
    pointer = ActiveProjectPointer(
        project_id=project_id.strip(),
        run_id=run_id.strip(),
        backend=backend.strip(),
        project_path=project_path.strip(),
        param_path=param_path.strip(),
        machine_path=machine_path.strip(),
    )
    if not pointer.project_id:
        raise ValueError("project_id is required")
    session.metadata[ACTIVE_PROJECT_METADATA_KEY] = pointer.to_dict()
    return pointer


def clear_active_project(session: Any) -> None:
    session.metadata.pop(ACTIVE_PROJECT_METADATA_KEY, None)


def format_active_project(session: Any) -> str:
    pointer = get_active_project(session)
    if pointer is None:
        return "Active project: none."
    return "Active MLP project:\n" + format_active_project_from_pointer(pointer)


def format_goal(session: Any) -> str:
    goal = get_goal(session)
    return f"Current goal:\n{goal}" if goal else "Goal: none."


def format_plan(session: Any) -> str:
    plan = get_plan(session)
    if not plan:
        return "Plan: none."
    lines = ["Current plan:"]
    for index, item in enumerate(plan, start=1):
        lines.append(f"{index}. [{item.status}] {item.step}")
    return "\n".join(lines)


def format_workstate_context(session: Any) -> str:
    parts: list[str] = []
    goal = get_goal(session)
    if goal:
        parts.extend(["Current Goal:", goal])
    plan = _active_plan_items(get_plan(session))
    if plan:
        if parts:
            parts.append("")
        parts.append("Current Plan:")
        for index, item in enumerate(plan, start=1):
            parts.append(f"{index}. [{item.status}] {item.step}")
    pointer = get_active_project(session)
    if pointer is not None:
        if parts:
            parts.append("")
        parts.append("[Active MLP Project]")
        for key, value in pointer.to_dict().items():
            parts.append(f"{key}: {value}")
        parts.extend([
            "status_source: call MCP tools for live state",
            "[/Active MLP Project]",
        ])
    return "\n".join(parts)


def format_workstate_summary_display(session: Any) -> str:
    goal_fallback = _fallback_goal_summary(session)
    plan_fallback = _fallback_plan_summary(session)
    goal = _get_summary(session, GOAL_SUMMARY_METADATA_KEY, goal_fallback) if goal_fallback else ""
    plan = _get_summary(session, PLAN_SUMMARY_METADATA_KEY, plan_fallback) if plan_fallback else ""
    return f"goal: {goal or '-'}\nplan: {plan or '-'}"


async def refresh_workstate_summary(
    session: Any,
    *,
    provider: Any,
    model: str | None,
    target: Literal["goal", "plan"],
) -> SummaryRefreshResult:
    """Refresh the short display summary with the active LLM provider."""
    source = _workstate_source(session, target)
    key = GOAL_SUMMARY_METADATA_KEY if target == "goal" else PLAN_SUMMARY_METADATA_KEY
    if not source:
        session.metadata.pop(key, None)
        return SummaryRefreshResult("")
    fallback = _fallback_goal_summary(session) if target == "goal" else _fallback_plan_summary(session)
    if provider is None or provider.__class__.__name__ == "TuiUnavailableProvider":
        session.metadata[key] = fallback
        return SummaryRefreshResult(fallback, error="provider unavailable")

    call = getattr(provider, "chat_with_retry", None) or getattr(provider, "chat", None)
    if not callable(call):
        session.metadata[key] = fallback
        return SummaryRefreshResult(fallback, error="provider unavailable")

    error = ""
    for attempt in range(2):
        messages = _summary_prompt_messages(source, target=target, retry=attempt > 0)
        try:
            response = await call(
                messages=messages,
                tools=None,
                model=model,
                temperature=0.0,
                tool_choice=None,
            )
        except Exception as exc:
            error = type(exc).__name__
            break

        finish_reason = str(getattr(response, "finish_reason", "") or "unknown")
        if finish_reason == "error":
            error = "provider error"
            break
        summary = _summary_from_response(response)
        if summary:
            if _workstate_source(session, target) != source:
                return SummaryRefreshResult("", error="stale")
            session.metadata[key] = summary
            return SummaryRefreshResult(summary, used_ai=True)
        error = _empty_summary_error(response)

    if _workstate_source(session, target) != source:
        return SummaryRefreshResult("", error="stale")
    session.metadata[key] = fallback
    return SummaryRefreshResult(fallback, error=error or "empty response")


async def refresh_workstate_summary_for_session(
    sessions: Any,
    session_key: str,
    *,
    provider: Any,
    model: str | None,
    target: Literal["goal", "plan"],
) -> SummaryRefreshResult:
    session = sessions.get_or_create(session_key)
    result = await refresh_workstate_summary(
        session,
        provider=provider,
        model=model,
        target=target,
    )
    if result.error != "stale":
        sessions.save(session)
    return result


def apply_goal_command(session: Any, args: str) -> str:
    text = args.strip()
    if not text:
        return format_goal(session)
    if text.lower() in {"clear", "reset", "none"}:
        set_goal(session, "")
        return "Goal cleared."
    goal = set_goal(session, text)
    return f"Goal set:\n{goal}"


def apply_plan_command(session: Any, args: str) -> str:
    text = args.strip()
    if not text:
        return format_plan(session)
    command, rest = _split_command(text)
    if command in {"clear", "reset"}:
        clear_plan(session)
        return "Plan cleared."
    if command == "add":
        step = rest.strip()
        if not step:
            return "Usage: /plan add <step>"
        plan = get_plan(session)
        plan.append(PlanItem(step=step))
        set_plan(session, plan)
        _refresh_plan_fallback_summary(session)
        return format_plan(session)
    if command in {"done", "complete", "completed"}:
        return _apply_plan_status(session, rest, "completed")
    if command in {"doing", "start", "in-progress", "in_progress"}:
        return _apply_plan_status(session, rest, "in_progress")
    if command in {"pending", "todo"}:
        return _apply_plan_status(session, rest, "pending")
    if command in {"remove", "rm", "delete"}:
        return _remove_plan_item(session, rest)
    if command == "set":
        text = rest.strip()
        if not text:
            return "Usage: /plan set <step or checklist>"
    plan = parse_plan_text(text)
    set_plan(session, plan)
    _refresh_plan_fallback_summary(session)
    return format_plan(session)


def apply_project_command(session: Any, args: str, *, workspace: Path | str | None = None) -> str:
    text = args.strip()
    if not text:
        return format_active_project(session)
    command, rest = _split_command(text)
    if command in {"clear", "reset", "none"}:
        clear_active_project(session)
        return "Active project cleared."
    if command == "set":
        text = rest.strip()
    pieces = text.split()
    if not pieces:
        return "Usage: /project [set] <project_id> [run_id] | clear"
    project_id = pieces[0]
    run_id = pieces[1] if len(pieces) > 1 else ""
    pointer = set_active_project(
        session,
        **_project_pointer_from_workspace(project_id, run_id, workspace),
    )
    return "Active project set:\n" + format_active_project_from_pointer(pointer)


def format_active_project_from_pointer(pointer: ActiveProjectPointer) -> str:
    lines = [f"{key}: {value}" for key, value in pointer.to_dict().items()]
    lines.append("status_source: call MCP tools for live state")
    return "\n".join(lines)


def parse_plan_text(text: str) -> list[PlanItem]:
    items: list[PlanItem] = []
    for raw_line in text.splitlines():
        step, status = _parse_plan_line(raw_line)
        if step:
            items.append(PlanItem(step=step, status=status))
    if not items and text.strip():
        items.append(PlanItem(step=text.strip()))
    return items


def _split_command(text: str) -> tuple[str, str]:
    parts = text.split(maxsplit=1)
    if not parts:
        return "", ""
    return parts[0].lower(), parts[1] if len(parts) > 1 else ""


def _project_pointer_from_workspace(
    project_id: str,
    run_id: str,
    workspace: Path | str | None,
) -> dict[str, str]:
    if workspace is None:
        return {"project_id": project_id, "run_id": run_id}

    from mlpcopilot.runtime.workspace import load_mlp_project, load_mlp_run

    workspace_path = Path(workspace).expanduser()
    project = load_mlp_project(workspace_path, project_id)
    resolved_run_id = run_id or str(project.get("active_run_id") or "")
    payload = {"project_id": project_id, "run_id": resolved_run_id}
    if not resolved_run_id:
        return payload

    run = load_mlp_run(workspace_path, project_id, resolved_run_id)
    backend = str(run.get("backend") or "")
    backend_workdir = str(run.get("backend_workdir") or "")
    run_dir = workspace_path / "projects" / project_id / "runs" / resolved_run_id
    project_path = run_dir / backend_workdir if backend_workdir else run_dir
    payload.update(
        {
            "backend": backend,
            "project_path": str(project_path),
            "param_path": str(project_path / "param.json"),
            "machine_path": str(project_path / "machine.json"),
        }
    )
    return payload


def _parse_plan_line(raw_line: str) -> tuple[str, PlanStatus]:
    line = raw_line.strip()
    if not line:
        return "", "pending"
    for prefix in ("-", "*"):
        if line.startswith(prefix):
            line = line[1:].strip()
            break
    if line[:2].isdigit() and len(line) > 2 and line[2] in {".", ")"}:
        line = line[3:].strip()
    lowered = line.lower()
    markers: tuple[tuple[str, PlanStatus], ...] = (
        ("[x]", "completed"),
        ("[done]", "completed"),
        ("[~]", "in_progress"),
        ("[doing]", "in_progress"),
        ("[ ]", "pending"),
        ("[todo]", "pending"),
        ("[pending]", "pending"),
    )
    for marker, status in markers:
        if lowered.startswith(marker):
            return line[len(marker):].strip(), status
    return line, "pending"


def _apply_plan_status(session: Any, raw_index: str, status: PlanStatus) -> str:
    index = _parse_index(raw_index)
    if index is None:
        return "Usage: /plan done|doing|pending <item_number>"
    plan = get_plan(session)
    if index < 1 or index > len(plan):
        return f"Plan item not found: {index}"
    updated: list[PlanItem] = []
    for offset, item in enumerate(plan, start=1):
        next_status = item.status
        if offset == index:
            next_status = status
        elif status == "in_progress" and item.status == "in_progress":
            next_status = "pending"
        updated.append(PlanItem(step=item.step, status=next_status))
    set_plan(session, updated)
    _refresh_plan_fallback_summary(session)
    return format_plan(session)


def _remove_plan_item(session: Any, raw_index: str) -> str:
    index = _parse_index(raw_index)
    if index is None:
        return "Usage: /plan remove <item_number>"
    plan = get_plan(session)
    if index < 1 or index > len(plan):
        return f"Plan item not found: {index}"
    del plan[index - 1]
    set_plan(session, plan)
    _refresh_plan_fallback_summary(session)
    return format_plan(session)


def _parse_index(value: str) -> int | None:
    try:
        return int(value.strip().split(maxsplit=1)[0])
    except (IndexError, ValueError):
        return None


def _normalize_plan(plan: list[PlanItem]) -> list[PlanItem]:
    seen_in_progress = False
    normalized: list[PlanItem] = []
    for item in plan:
        step = item.step.strip()
        if not step:
            continue
        status = item.status if item.status in _VALID_STATUSES else "pending"
        if status == "in_progress":
            if seen_in_progress:
                status = "pending"
            seen_in_progress = True
        normalized.append(PlanItem(step=step, status=status))
    return normalized


def compact_workstate_summary(value: str, *, max_units: int = 20) -> str:
    value = " ".join(value.replace("\n", " ").split()).strip("`'\"“”‘’。；;,.，")
    if not value:
        return ""
    if _CJK_RE.search(value):
        chars = [char for char in value if not char.isspace()]
        return "".join(chars[:max_units])
    words = value.split()
    return " ".join(words[:max_units])


def _get_summary(session: Any, key: str, fallback: str) -> str:
    value = getattr(session, "metadata", {}).get(key)
    if isinstance(value, str) and value.strip():
        return compact_workstate_summary(value)
    return fallback


def _fallback_goal_summary(session: Any) -> str:
    return compact_workstate_summary(get_goal(session))


def _fallback_plan_summary(session: Any) -> str:
    plan = _active_plan_items(get_plan(session))
    if not plan:
        return ""
    for status in ("in_progress", "pending"):
        candidates = [item for item in plan if item.status == status]
        if candidates:
            return compact_workstate_summary(candidates[0].step)
    return ""


def _refresh_plan_fallback_summary(session: Any) -> None:
    summary = _fallback_plan_summary(session)
    if summary:
        session.metadata[PLAN_SUMMARY_METADATA_KEY] = summary
    else:
        session.metadata.pop(PLAN_SUMMARY_METADATA_KEY, None)


def _active_plan_items(plan: list[PlanItem]) -> list[PlanItem]:
    return [item for item in plan if item.status in {"in_progress", "pending"}]


def _workstate_source(session: Any, target: Literal["goal", "plan"]) -> str:
    if target == "goal":
        return get_goal(session)
    return format_plan(session) if get_plan(session) else ""


def _summary_from_response(response: Any) -> str:
    content = str(getattr(response, "content", "") or "")
    return compact_workstate_summary(strip_think(content))


def _empty_summary_error(response: Any) -> str:
    finish_reason = str(getattr(response, "finish_reason", "") or "unknown")
    reasoning = str(getattr(response, "reasoning_content", "") or "").strip()
    if reasoning:
        return f"empty response finish={finish_reason} reasoning_only"
    return f"empty response finish={finish_reason}"


def _summary_prompt_messages(
    source: str,
    *,
    target: Literal["goal", "plan"],
    retry: bool = False,
) -> list[dict[str, str]]:
    kind = "goal" if target == "goal" else "plan"
    retry_line = (
        "The previous answer had empty visible content. "
        "Now answer with only the visible summary text, no thinking or explanation. "
        if retry else ""
    )
    return [
        {
            "role": "system",
            "content": (
                "You summarize a runtime work goal or plan for a terminal status bar. "
                "Return only one concise summary. No label, no markdown, no quotes, no newline. "
                "Preserve the user's intent. Do not copy the source unless it is already minimal. "
                "Use the same language as the source. Limit English to 20 words and CJK text to 20 characters. "
                f"{retry_line}"
            ),
        },
        {
            "role": "user",
            "content": f"Summarize this {kind}:\n{source}",
        },
    ]
