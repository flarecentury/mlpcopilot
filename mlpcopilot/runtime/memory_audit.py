"""Read-only durable memory hygiene checks for MLP Copilot workspaces."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class MemoryAuditFinding:
    """A likely stale or transient fact found in durable memory."""

    line_no: int
    category: str
    detail: str
    text: str


_DYNAMIC_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "dpgen-iteration",
        "current DP-GEN iteration/stage should be read from record.dpgen or MCP status tools",
        re.compile(r"\b(iter\.\d{6}|current[_ -]?(iteration|stage)|active[_ -]?(iteration|stage))\b", re.I),
    ),
    (
        "dpgen-stage",
        "stage names are live workflow state, not durable memory",
        re.compile(
            r"\b(make_train|run_train|post_train|make_model_devi|run_model_devi|"
            r"post_model_devi|make_fp|run_fp|post_fp)\b",
            re.I,
        ),
    ),
    (
        "queue-counts",
        "queue/task counts change during a run and should come from tools",
        re.compile(r"\b(queue|submitted|running|done|recovered|failed|candidate|accurate|sub|rec|err)\b.*\b\d+\b", re.I),
    ),
    (
        "transient-error",
        "dispatcher errors and tracebacks should be cited from logs, not memorized as current truth",
        re.compile(r"\b(dpdispatcher\.log|error\.log|traceback|keyboard interrupt|bad gateway|502)\b", re.I),
    ),
    (
        "runtime-status",
        "current status should be refreshed from MCP/artifacts before use",
        re.compile(r"\b(current status|currently running|currently active|next stage|active run|run_local)\b", re.I),
    ),
)

_STABLE_CONTEXT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bdo not\b", re.I),
    re.compile(r"\bmust\b", re.I),
    re.compile(r"\bshould\b", re.I),
    re.compile(r"\bsource of truth\b", re.I),
    re.compile(r"\bstatus_source\b", re.I),
)


def memory_file_path(workspace: Path | str) -> Path:
    """Return the durable memory file path for a workspace."""
    return Path(workspace) / "memory" / "MEMORY.md"


def audit_memory_file(path: Path | str) -> list[MemoryAuditFinding]:
    """Scan a memory file for likely stale DP-GEN/runtime facts.

    This is intentionally heuristic and read-only. It reports lines that look
    like transient workflow state, while avoiding policy lines such as
    "do not store current iteration".
    """
    memory_path = Path(path)
    if not memory_path.exists():
        return []

    findings: list[MemoryAuditFinding] = []
    for line_no, raw_line in enumerate(memory_path.read_text(encoding="utf-8").splitlines(), start=1):
        text = raw_line.strip()
        if not text or _looks_like_policy_line(text):
            continue
        for category, detail, pattern in _DYNAMIC_PATTERNS:
            if pattern.search(text):
                findings.append(MemoryAuditFinding(
                    line_no=line_no,
                    category=category,
                    detail=detail,
                    text=_clip(text),
                ))
                break
    return findings


def audit_workspace_memory(workspace: Path | str) -> tuple[Path, list[MemoryAuditFinding]]:
    """Scan the default durable memory file in a workspace."""
    path = memory_file_path(workspace)
    return path, audit_memory_file(path)


def format_memory_audit_report(workspace: Path | str) -> str:
    """Build a compact user-facing memory hygiene report."""
    path, findings = audit_workspace_memory(workspace)
    lines = [
        "Memory audit",
        f"File: {path}",
        "",
    ]
    if not path.exists():
        lines.append("No memory file found.")
        return "\n".join(lines)
    if not findings:
        lines.append("No likely stale runtime facts found.")
        return "\n".join(lines)

    lines.append(f"Found {len(findings)} likely stale runtime fact(s):")
    for finding in findings[:50]:
        lines.append(
            f"- L{finding.line_no} [{finding.category}] {finding.text}"
        )
        lines.append(f"  Suggestion: {finding.detail}.")
    if len(findings) > 50:
        lines.append(f"- ... {len(findings) - 50} more finding(s) omitted.")
    lines.extend([
        "",
        "Review these manually. This command is read-only and does not edit memory.",
    ])
    return "\n".join(lines)


def _looks_like_policy_line(text: str) -> bool:
    lowered = text.lower()
    if "not" in lowered and any(word in lowered for word in ("store", "trust", "memorize", "promote")):
        return True
    return any(pattern.search(text) for pattern in _STABLE_CONTEXT_PATTERNS) and "current" in lowered


def _clip(text: str, limit: int = 180) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}..."
