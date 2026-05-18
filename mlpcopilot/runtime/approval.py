"""ApprovalManager for human-in-the-loop runtime decisions."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

ApprovalStatus = Literal[
    "pending",
    "approved",
    "partially_approved",
    "rejected",
    "needs_changes",
    "expired",
]

DecisionStatus = Literal["approved", "partially_approved", "rejected", "needs_changes", "expired"]

def _now() -> str:
    return datetime.now(tz=UTC).isoformat()


@dataclass(slots=True)
class ApprovalRecord:
    """A durable approval request or decision record."""

    approval_id: str
    action_type: str
    title: str
    request: str
    status: ApprovalStatus = "pending"
    created_at: str = field(default_factory=_now)
    requester: str | None = None
    run_id: str | None = None
    expires_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    decided_at: str | None = None
    decided_by: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "action_type": self.action_type,
            "title": self.title,
            "request": self.request,
            "status": self.status,
            "created_at": self.created_at,
            "requester": self.requester,
            "run_id": self.run_id,
            "expires_at": self.expires_at,
            "metadata": self.metadata,
            "decided_at": self.decided_at,
            "decided_by": self.decided_by,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApprovalRecord":
        return cls(
            approval_id=str(data["approval_id"]),
            action_type=str(data.get("action_type") or "unknown"),
            title=str(data.get("title") or data.get("action_type") or "Approval"),
            request=str(data.get("request") or ""),
            status=data.get("status") or "pending",
            created_at=str(data.get("created_at") or _now()),
            requester=data.get("requester"),
            run_id=data.get("run_id"),
            expires_at=data.get("expires_at"),
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
            decided_at=data.get("decided_at"),
            decided_by=data.get("decided_by"),
            reason=data.get("reason"),
        )


def _safe_scope_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return name.strip("._-") or "default"


class ApprovalManager:
    """Persist and decide approval records in the active workspace."""

    def __init__(self, workspace: Path, session_key: str | None = None):
        self.workspace = workspace.expanduser()
        self.session_key = session_key
        self.approvals_dir = self._approval_dir(session_key)
        self.pending_path = self.approvals_dir / "pending.jsonl"
        self.decisions_path = self.approvals_dir / "decisions.jsonl"
        self.approvals_dir.mkdir(parents=True, exist_ok=True)
        self.pending_path.touch(exist_ok=True)
        self.decisions_path.touch(exist_ok=True)

    def _approval_dir(self, session_key: str | None) -> Path:
        base = self.workspace / "approvals"
        if not session_key:
            return base
        return base / "sessions" / _safe_scope_name(session_key)

    def create(
        self,
        *,
        action_type: str,
        title: str,
        request: str,
        requester: str | None = None,
        run_id: str | None = None,
        expires_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ApprovalRecord:
        record = ApprovalRecord(
            approval_id=f"apr_{uuid.uuid4().hex[:12]}",
            action_type=action_type,
            title=title,
            request=request,
            requester=requester,
            run_id=run_id,
            expires_at=expires_at,
            metadata=metadata or {},
        )
        self._append_jsonl(self.pending_path, record.to_dict())
        return record

    def list_pending(self) -> list[ApprovalRecord]:
        return [record for record in self._read_records(self.pending_path) if record.status == "pending"]

    def list_decisions(self) -> list[ApprovalRecord]:
        return self._read_records(self.decisions_path)

    def get(self, approval_id: str) -> ApprovalRecord | None:
        for record in self.list_pending():
            if record.approval_id == approval_id:
                return record
        for record in reversed(self.list_decisions()):
            if record.approval_id == approval_id:
                return record
        return None

    def decide(
        self,
        approval_id: str,
        *,
        status: DecisionStatus,
        decided_by: str | None = None,
        reason: str | None = None,
    ) -> ApprovalRecord:
        pending = self.list_pending()
        match: ApprovalRecord | None = None
        remaining: list[ApprovalRecord] = []
        for record in pending:
            if record.approval_id == approval_id and match is None:
                match = record
            else:
                remaining.append(record)
        if match is None:
            existing = self.get(approval_id)
            if existing is not None:
                raise ValueError(f"Approval {approval_id} is already {existing.status}")
            raise KeyError(f"Approval not found: {approval_id}")

        match.status = status
        match.decided_at = _now()
        match.decided_by = decided_by
        match.reason = reason
        self._write_records(self.pending_path, remaining)
        self._append_jsonl(self.decisions_path, match.to_dict())
        self._sync_run_manifest(match)
        return match

    def approve(self, approval_id: str, *, decided_by: str | None = None, reason: str | None = None) -> ApprovalRecord:
        return self.decide(approval_id, status="approved", decided_by=decided_by, reason=reason)

    def reject(self, approval_id: str, *, decided_by: str | None = None, reason: str | None = None) -> ApprovalRecord:
        return self.decide(approval_id, status="rejected", decided_by=decided_by, reason=reason)

    def needs_changes(self, approval_id: str, *, decided_by: str | None = None, reason: str | None = None) -> ApprovalRecord:
        return self.decide(approval_id, status="needs_changes", decided_by=decided_by, reason=reason)

    def approve_or_get(
        self,
        approval_id: str,
        *,
        decided_by: str | None = None,
        reason: str | None = None,
    ) -> tuple[ApprovalRecord, bool]:
        """Approve a pending record, or return an already-approved decision."""
        try:
            return self.approve(approval_id, decided_by=decided_by, reason=reason), True
        except ValueError:
            existing = self.get(approval_id)
            if existing is not None and existing.status in {"approved", "partially_approved"}:
                return existing, False
            raise

    def _read_records(self, path: Path) -> list[ApprovalRecord]:
        records: list[ApprovalRecord] = []
        if not path.exists():
            return records
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(raw, dict) and raw.get("approval_id"):
                records.append(ApprovalRecord.from_dict(raw))
        return records

    @staticmethod
    def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    @staticmethod
    def _write_records(path: Path, records: list[ApprovalRecord]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = "".join(json.dumps(r.to_dict(), ensure_ascii=False, sort_keys=True) + "\n" for r in records)
        path.write_text(text, encoding="utf-8")

    def _sync_run_manifest(self, record: ApprovalRecord) -> None:
        """Best-effort link from an approval decision back to its run manifest."""
        if not record.run_id:
            return
        try:
            from mlpcopilot.runtime.artifacts import ArtifactIndex

            index = ArtifactIndex(self.workspace)
            manifest = index.load(record.run_id)
            decision = record.to_dict()
            manifest.approval = decision
            manifest.decisions = _upsert_manifest_decision(manifest.decisions, decision)
            index.save(manifest)
        except (FileNotFoundError, ValueError, OSError, json.JSONDecodeError):
            return


def _upsert_manifest_decision(decisions: list[Any], decision: dict[str, Any]) -> list[Any]:
    approval_id = decision.get("approval_id")
    if not approval_id:
        return [*decisions, decision]
    updated: list[Any] = []
    replaced = False
    for item in decisions:
        if isinstance(item, dict) and item.get("approval_id") == approval_id:
            updated.append(decision)
            replaced = True
        else:
            updated.append(item)
    if not replaced:
        updated.append(decision)
    return updated


def tool_requires_approval(
    tool_name: str,
    tool: Any | None = None,
    *,
    arguments: dict[str, Any] | None = None,
    workspace: Path | None = None,
    approval_allowlist: list[str] | tuple[str, ...] | set[str] | None = None,
) -> bool:
    """Return whether a tool call should be approval-gated by runtime policy."""
    if tool_name in set(approval_allowlist or ()):
        return False
    if getattr(tool, "read_only", False) is True:
        return False
    if tool_name == "exec" and getattr(tool, "approval_required", False):
        # ExecTool has command-exact allowCommands support and can create
        # command-specific approval records itself. Let it own that flow so
        # exact allowlisted commands run without a second, generic approval.
        return False
    if workspace is not None and _is_invalid_file_tool_operation(workspace, tool_name, arguments or {}):
        return False
    return True


def tool_approval_error(
    workspace: Path,
    *,
    tool_name: str,
    arguments: dict[str, Any],
    tool: Any | None = None,
    approval_allowlist: list[str] | tuple[str, ...] | set[str] | None = None,
    session_key: str | None = None,
) -> str | None:
    """Create or find an approval record for a side-effecting tool call."""
    if not tool_requires_approval(
        tool_name,
        tool,
        arguments=arguments,
        workspace=workspace,
        approval_allowlist=approval_allowlist,
    ):
        return None

    manager = ApprovalManager(workspace, session_key=session_key)
    normalized_args = _approval_json(arguments)
    args_hash = _approval_args_hash(normalized_args)

    record = _find_pending_tool_approval(manager, tool_name, args_hash)
    if record is None:
        metadata = {
            "tool": tool_name,
            "arguments": normalized_args,
            "args_hash": args_hash,
        }
        if session_key:
            metadata["session_key"] = session_key
        rel_path = _approval_relative_path(workspace, normalized_args.get("path"))
        if rel_path is not None:
            metadata["path"] = rel_path
        if tool_name in {"write_file", "edit_file", "notebook_edit"}:
            metadata.update(_file_tool_risk_metadata(rel_path))
        if tool_name == "exec":
            command = normalized_args.get("command")
            working_dir = normalized_args.get("working_dir")
            if isinstance(command, str):
                metadata["command"] = command
            if isinstance(working_dir, str):
                metadata["working_dir"] = str(Path(working_dir).expanduser().resolve())
        run_id = normalized_args.get("run_id")
        record = manager.create(
            action_type="tool_execution",
            title=_approval_title(tool_name, normalized_args),
            request=_approval_request(tool_name, normalized_args),
            requester="agent",
            run_id=run_id.strip() if isinstance(run_id, str) and run_id.strip() else None,
            metadata=metadata,
        )
    if session_key:
        return (
            f"Error: Approval required before executing tool {tool_name}. "
            f"Approval ID: {record.approval_id}. "
            f"Approve in this TUI session with /approve {record.approval_id}."
        )
    return (
        f"Error: Approval required before executing tool {tool_name}. "
        f"Approval ID: {record.approval_id}. "
        f"Approve with /approve {record.approval_id} or "
        f"mlpcopilot mlp approve {record.approval_id}."
    )


def _approval_json(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))
    except (TypeError, ValueError):
        return str(value)


def _approval_args_hash(arguments: Any) -> str:
    payload = json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_new_file_operation(
    workspace: Path,
    tool_name: str,
    arguments: dict[str, Any],
) -> bool:
    if tool_name == "write_file":
        return _path_is_new_workspace_file(workspace, arguments.get("path"))
    if tool_name == "edit_file" and arguments.get("old_text") == "":
        return _path_is_new_workspace_file(workspace, arguments.get("path"))
    return False


_BINARY_EDIT_SUFFIXES = frozenset({
    ".bin",
    ".ckpt",
    ".dump",
    ".gz",
    ".h5",
    ".hdf5",
    ".npy",
    ".npz",
    ".pb",
    ".pth",
    ".tar",
    ".tgz",
    ".zip",
})


def _is_invalid_file_tool_operation(
    workspace: Path,
    tool_name: str,
    arguments: dict[str, Any],
) -> bool:
    path = _resolve_workspace_path(workspace, arguments.get("path"))
    if path is None:
        return False
    if tool_name != "edit_file":
        return False
    if arguments.get("old_text") == arguments.get("new_text"):
        return True
    if not path.exists() or not path.is_file():
        return False
    if path.suffix.lower() in _BINARY_EDIT_SUFFIXES:
        return True
    try:
        with path.open("rb") as handle:
            sample = handle.read(8192)
    except OSError:
        return False
    if b"\x00" in sample:
        return True
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def _path_is_new_workspace_file(workspace: Path, raw_path: Any) -> bool:
    path = _resolve_workspace_path(workspace, raw_path)
    if path is None:
        return False
    return not path.exists()


def _workspace_relative_path(workspace: Path, path: Path) -> str | None:
    try:
        return path.relative_to(workspace.expanduser().resolve()).as_posix()
    except ValueError:
        return None


def _approval_relative_path(workspace: Path, raw_path: Any) -> str | None:
    path = _resolve_workspace_path(workspace, raw_path)
    if path is None:
        return None
    try:
        return str(path.relative_to(workspace.expanduser().resolve()))
    except ValueError:
        return str(path)


def _resolve_workspace_path(workspace: Path, raw_path: Any) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    root = workspace.expanduser().resolve()
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    lexical = Path(os.path.abspath(candidate))
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError:
        try:
            lexical.relative_to(root)
        except ValueError:
            return None
    return resolved


def _file_tool_risk_metadata(rel_path: str | None) -> dict[str, str]:
    rel = (rel_path or "").replace("\\", "/")
    if not rel:
        return {
            "risk_level": "high",
            "risk_reason": "file mutation target could not be reduced to a workspace-relative path",
        }
    if rel.startswith("/"):
        return {
            "risk_level": "critical",
            "risk_reason": "resolved target is outside workspace, likely through a symlink or external backend",
        }
    if "/backend/" in rel:
        return {
            "risk_level": "critical",
            "risk_reason": "training backend or raw run artifact mutation",
        }
    managed_prefixes = ("sessions/", "logs/", "approvals/", "artifacts/", "memory/")
    managed_files = {"SOUL.md", "PROJECT.md", "USER.md", "AGENTS.md", "TOOLS.md", "HEARTBEAT.md"}
    if rel.startswith(managed_prefixes) or rel in managed_files:
        return {
            "risk_level": "high",
            "risk_reason": "runtime-managed or agent-managed state mutation",
        }
    return {
        "risk_level": "medium",
        "risk_reason": "workspace file mutation",
    }


def _approval_title(tool_name: str, normalized_args: Any) -> str:
    if tool_name.startswith("mcp_"):
        return f"Approve MCP tool: {tool_name}"
    if tool_name in {"write_file", "edit_file", "notebook_edit"}:
        path = normalized_args.get("path") if isinstance(normalized_args, dict) else None
        suffix = f" on {path}" if isinstance(path, str) else ""
        return f"Approve {tool_name}{suffix}"
    return f"Approve {tool_name}: {_short_json(normalized_args, 80)}"


def _approval_request(tool_name: str, normalized_args: Any) -> str:
    args_text = json.dumps(normalized_args, ensure_ascii=False, sort_keys=True)
    if tool_name.startswith("mcp_"):
        return (
            "An MCP tool call can run external plugin code and may create or "
            "modify artifacts.\n\n"
            f"Tool: {tool_name}\nArguments: {args_text}"
        )
    if tool_name in {"write_file", "edit_file", "notebook_edit"}:
        return (
            f"{tool_name} wants to modify an existing file.\n\n"
            f"Arguments: {args_text}"
        )
    return f"{tool_name} wants to execute with these arguments:\n{args_text}"


def _find_pending_tool_approval(
    manager: ApprovalManager,
    tool_name: str,
    args_hash: str,
) -> ApprovalRecord | None:
    for record in manager.list_pending():
        metadata = record.metadata or {}
        if (
            record.action_type == "tool_execution"
            and metadata.get("tool") == tool_name
            and metadata.get("args_hash") == args_hash
        ):
            return record
    return None


def _short_json(value: Any, limit: int) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _approval_result_display(tool_name: str, result: Any) -> str:
    text = str(result)
    if tool_name.startswith("mcp_"):
        answer = _extract_mcp_answer(text)
        if answer:
            return _limit_approval_result(answer)
    return _limit_approval_result(text)


def _extract_mcp_answer(text: str) -> str | None:
    payload = _json_loads_maybe(text)
    return _extract_answer_from_payload(payload)


def _json_loads_maybe(text: str) -> Any | None:
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _extract_answer_from_payload(payload: Any) -> str | None:
    if isinstance(payload, dict):
        answer = payload.get("answer")
        if isinstance(answer, str) and answer.strip():
            return answer.strip()
        result = payload.get("result")
        if isinstance(result, str):
            nested = _extract_answer_from_payload(_json_loads_maybe(result))
            if nested:
                return nested
            if result.strip():
                return result.strip()
        structured = payload.get("structuredContent") or payload.get("structured_content")
        nested = _extract_answer_from_payload(structured)
        if nested:
            return nested
        content = payload.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    item_text = item.get("text")
                    if isinstance(item_text, str) and item_text.strip():
                        nested = _extract_answer_from_payload(_json_loads_maybe(item_text))
                        parts.append(nested or item_text.strip())
            if parts:
                return "\n".join(parts)
    if isinstance(payload, str) and payload.strip():
        return payload.strip()
    return None


def _limit_approval_result(text: str, limit: int = 8000) -> str:
    stripped = text.rstrip()
    if len(stripped) <= limit:
        return stripped
    truncated = stripped[: limit - 80].rstrip()
    return (
        f"{truncated}\n\n"
        "[tool result truncated; ask a narrower follow-up if you need more details]"
    )


def _approval_resume_label(tool_name: str) -> str:
    if tool_name.startswith("mcp_"):
        return "MCP tool"
    return tool_name


async def resume_approved_action(loop: Any, record: ApprovalRecord) -> str | None:
    """Resume a runtime action after its approval is accepted.

    Write approvals are durable decisions only because their pending records do
    not store file content. Tool execution approvals store their original
    arguments and can be replayed.
    """
    if record.status not in {"approved", "partially_approved"}:
        return None
    metadata = record.metadata or {}
    tool_name = metadata.get("tool")
    if not isinstance(tool_name, str):
        return None

    arguments = metadata.get("arguments")
    if record.action_type in {"exec_command", "destructive_exec"}:
        command = metadata.get("command")
        working_dir = metadata.get("working_dir")
        if not isinstance(command, str) or not command.strip():
            return "Approved, but exec command metadata is missing; nothing was resumed."
        arguments = {"command": command}
        if isinstance(working_dir, str):
            arguments["working_dir"] = working_dir
        background = metadata.get("background")
        if isinstance(background, bool):
            arguments["background"] = background
        elif isinstance(metadata.get("arguments"), dict):
            raw_background = metadata["arguments"].get("background")
            if isinstance(raw_background, bool):
                arguments["background"] = raw_background
    elif record.action_type != "tool_execution":
        return None

    if not isinstance(arguments, dict):
        return f"Approved, but {tool_name} arguments are missing; nothing was resumed."

    tools = getattr(loop, "tools", None)
    get_tool = getattr(tools, "get", None)
    tool = get_tool(tool_name) if callable(get_tool) else None
    execute = getattr(tool, "execute", None)
    call_args = dict(arguments)
    if tool_name == "exec" or _tool_accepts_approval_id(tool):
        call_args["approval_id"] = record.approval_id
    if callable(execute):
        result = await execute(**call_args)
    else:
        registry_execute = getattr(tools, "execute", None)
        if not callable(registry_execute):
            return (
                f"Approved, but tool {tool_name} is unavailable in this runtime; "
                "nothing was resumed."
            )
        result = await registry_execute(tool_name, call_args)
    _sync_resumed_action_manifest(loop, record)
    label = _approval_resume_label(tool_name)
    return f"Resumed {label} after approval:\n{_approval_result_display(tool_name, result)}"


def _sync_resumed_action_manifest(loop: Any, record: ApprovalRecord) -> None:
    """Retry run-manifest decision sync after a resumed tool has created artifacts."""
    if not record.run_id:
        return
    workspace = getattr(loop, "workspace", None)
    if workspace is None:
        return
    session_key = record.metadata.get("session_key") if isinstance(record.metadata, dict) else None
    try:
        ApprovalManager(
            Path(workspace),
            session_key=session_key if isinstance(session_key, str) else None,
        )._sync_run_manifest(record)
    except Exception:
        return


def _tool_accepts_approval_id(tool: Any | None) -> bool:
    parameters = getattr(tool, "parameters", None)
    if isinstance(parameters, dict):
        properties = parameters.get("properties")
        if isinstance(properties, dict) and "approval_id" in properties:
            return True
    return False
