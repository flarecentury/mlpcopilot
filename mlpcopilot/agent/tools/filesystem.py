"""File system tools: read, write, edit, list."""

import difflib
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mlpcopilot.agent.tools.base import Tool, tool_parameters
from mlpcopilot.agent.tools.file_state import FileStates, _hash_file, current_file_states
from mlpcopilot.agent.tools.schema import (
    BooleanSchema,
    IntegerSchema,
    StringSchema,
    tool_parameters_schema,
)
from mlpcopilot.config.paths import get_media_dir
from mlpcopilot.utils.helpers import build_image_content_blocks, detect_image_mime


def _resolve_path(
    path: str,
    workspace: Path | None = None,
    allowed_dir: Path | None = None,
    extra_allowed_dirs: list[Path] | None = None,
) -> Path:
    """Resolve path against workspace (if relative) and enforce directory restriction."""
    p = Path(path).expanduser()
    if not p.is_absolute() and workspace:
        p = workspace / p
    lexical = Path(os.path.abspath(p))
    resolved = p.resolve(strict=False)
    if allowed_dir:
        media_path = get_media_dir().resolve()
        all_dirs = [allowed_dir] + [media_path] + (extra_allowed_dirs or [])
        if not any(_is_under(resolved, d) or _is_under(lexical, d) for d in all_dirs):
            raise PermissionError(f"Path {path} is outside allowed directory {allowed_dir}")
    return resolved


def _is_under(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory.resolve())
        return True
    except ValueError:
        return False


class _FsTool(Tool):
    """Shared base for filesystem tools — common init and path resolution."""

    def __init__(
        self,
        workspace: Path | None = None,
        allowed_dir: Path | None = None,
        extra_allowed_dirs: list[Path] | None = None,
        write_allowlist: list[str] | None = None,
        approval_gated_writes: bool = False,
        file_states: FileStates | None = None,
    ):
        self._workspace = workspace
        self._allowed_dir = allowed_dir
        self._extra_allowed_dirs = extra_allowed_dirs
        self._write_allowlist = tuple(write_allowlist or ())
        self._approval_gated_writes = approval_gated_writes
        # Explicit state is used by isolated runners like Dream/subagents.
        # Main AgentLoop tools leave this unset and resolve state from the
        # current async task, which keeps shared tool instances session-safe.
        self._explicit_file_states = file_states
        self._fallback_file_states = FileStates()

    @property
    def _file_states(self) -> FileStates:
        if self._explicit_file_states is not None:
            return self._explicit_file_states
        return current_file_states(self._fallback_file_states)

    def _resolve(self, path: str) -> Path:
        return _resolve_path(path, self._workspace, self._allowed_dir, self._extra_allowed_dirs)

    def _resolve_write(self, path: str) -> Path:
        resolved = self._resolve(path)
        return resolved

    def _protected_runtime_write_error(self, resolved: Path) -> str | None:
        if not self._workspace:
            return None
        try:
            rel_path = resolved.relative_to(self._workspace.resolve()).as_posix()
        except ValueError:
            return None
        if rel_path == "memory/history.jsonl":
            return (
                "Path memory/history.jsonl is runtime-managed append-only state and "
                "cannot be modified with generic write_file/edit_file tools. "
                "Use memory/runtime commands instead."
            )
        return None

    def _is_write_allowed(self, resolved: Path) -> bool:
        if not self._workspace:
            return True
        workspace = self._workspace.resolve()
        for entry in self._write_allowlist:
            raw = entry.strip()
            if not raw:
                continue
            configured = Path(raw).expanduser()
            target = configured if configured.is_absolute() else workspace / configured
            target = target.resolve(strict=False)
            file_entry = not raw.endswith(("/", os.sep)) and bool(configured.suffix)
            if file_entry:
                if resolved == target:
                    return True
                continue
            if resolved == target or _is_under(resolved, target):
                return True
        return False

    def _write_allowlist_error(self, resolved: Path) -> str | None:
        if not self._write_allowlist or self._is_write_allowed(resolved):
            return None
        rel_path = self._workspace_relative(resolved)
        return f"Error: {rel_path} is outside the write allowlist."

    def _write_approval_error(
        self,
        *,
        tool_name: str,
        resolved: Path,
        approval_id: str | None,
        overwrites_existing: bool,
    ) -> str | None:
        action_type = self._write_approval_action_type(resolved, overwrites_existing)
        if not action_type or not self._workspace:
            return None

        from mlpcopilot.agent.tools.session_context import current_session_key
        from mlpcopilot.runtime.approval import ApprovalManager

        session_key = current_session_key()
        manager = ApprovalManager(self._workspace, session_key=session_key)
        rel_path = self._workspace_relative(resolved)
        risk_metadata = self._write_risk_metadata(resolved, rel_path)
        if approval_id:
            record = manager.get(approval_id)
            if record is None:
                return f"Error: Approval not found: {approval_id}"
            if record.status not in {"approved", "partially_approved"}:
                return f"Error: Approval {approval_id} is {record.status}; write blocked."
            metadata = record.metadata or {}
            expected_path = metadata.get("path")
            expected_tool = metadata.get("tool")
            if expected_path and expected_path != rel_path:
                return (
                    f"Error: Approval {approval_id} is for {expected_path}, "
                    f"not {rel_path}; write blocked."
                )
            if expected_tool and expected_tool != tool_name:
                return (
                    f"Error: Approval {approval_id} is for {expected_tool}, "
                    f"not {tool_name}; write blocked."
                )
            return None

        record = self._find_pending_write_approval(manager, action_type, tool_name, rel_path)
        if record is None:
            record = manager.create(
                action_type=action_type,
                title=f"Approve {tool_name} on {rel_path}",
                request=(
                    f"{tool_name} wants to modify {rel_path}. "
                    f"Reason: {self._write_approval_reason(action_type)}. "
                    f"Risk: {risk_metadata['risk_level']} - {risk_metadata['risk_reason']}."
                ),
                requester="agent",
                metadata={
                    "tool": tool_name,
                    "path": rel_path,
                    "overwrites_existing": overwrites_existing,
                    **risk_metadata,
                    **({"session_key": session_key} if session_key else {}),
                },
            )
        if session_key:
            return (
                f"Error: Approval required before modifying {rel_path}. "
                f"Approval ID: {record.approval_id}. "
                f"Approve in this TUI session with /approve {record.approval_id}."
            )
        return (
            f"Error: Approval required before modifying {rel_path}. "
            f"Approval ID: {record.approval_id}. "
            f"Approve with /approve {record.approval_id} or "
            f"mlpcopilot mlp approve {record.approval_id}."
        )

    def _write_approval_action_type(self, resolved: Path, overwrites_existing: bool) -> str | None:
        if not self._approval_gated_writes or not self._workspace:
            return None
        workspace = self._workspace.resolve()
        rel_path = self._workspace_relative(resolved).replace("\\", "/")
        if (
            rel_path.startswith("sessions/")
            or rel_path.startswith("logs/")
            or rel_path.startswith("approvals/")
            or rel_path.startswith("artifacts/")
            or rel_path == "memory/history.jsonl"
        ):
            return "runtime_state_update"
        if resolved == (workspace / "PROJECT.md").resolve(strict=False):
            return "project_update"
        if _is_under(resolved, (workspace / "memory").resolve(strict=False)):
            return "memory_update"
        if overwrites_existing and _is_under(resolved, (workspace / "runs").resolve(strict=False)):
            return "run_artifact_overwrite"
        return "file_update"

    def _write_risk_metadata(self, resolved: Path, rel_path: str) -> dict[str, str]:
        rel = rel_path.replace("\\", "/")
        if rel.startswith("/"):
            return {
                "risk_level": "critical",
                "risk_reason": "resolved target is outside workspace, likely through a symlink or external backend",
            }
        if "/backend/" in rel or rel.startswith("projects/") and "/backend/" in rel:
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

    def _workspace_relative(self, resolved: Path) -> str:
        if not self._workspace:
            return str(resolved)
        try:
            return str(resolved.relative_to(self._workspace.resolve()))
        except ValueError:
            return str(resolved)

    @staticmethod
    def _write_approval_reason(action_type: str) -> str:
        reasons = {
            "file_update": "modifying an existing file requires human confirmation",
            "memory_update": "long-term memory changes require human confirmation",
            "project_update": "project-level criteria and decisions require human confirmation",
            "run_artifact_overwrite": "existing run artifacts must not be overwritten without approval",
        }
        return reasons.get(action_type, "this write is gated by runtime policy")

    @staticmethod
    def _find_pending_write_approval(
        manager: Any,
        action_type: str,
        tool_name: str,
        rel_path: str,
    ) -> Any | None:
        for record in manager.list_pending():
            metadata = record.metadata or {}
            if (
                record.action_type == action_type
                and metadata.get("tool") == tool_name
                and metadata.get("path") == rel_path
            ):
                return record
        return None


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------


_BLOCKED_DEVICE_PATHS = frozenset({
    "/dev/zero", "/dev/random", "/dev/urandom", "/dev/full",
    "/dev/stdin", "/dev/stdout", "/dev/stderr",
    "/dev/tty", "/dev/console",
    "/dev/fd/0", "/dev/fd/1", "/dev/fd/2",
})


def _is_blocked_device(path: str | Path) -> bool:
    """Check if path is a blocked device that could hang or produce infinite output."""
    import re
    raw = str(path)

    # Resolve symlinks to check the actual target
    try:
        resolved = str(Path(raw).resolve())
    except (OSError, ValueError):
        resolved = raw

    if raw in _BLOCKED_DEVICE_PATHS or resolved in _BLOCKED_DEVICE_PATHS:
        return True
    if re.match(r"/proc/\d+/fd/[012]$", raw) or re.match(r"/proc/self/fd/[012]$", raw):
        return True
    if re.match(r"/proc/\d+/fd/[012]$", resolved) or re.match(r"/proc/self/fd/[012]$", resolved):
        return True

    # Check if resolved path starts with /dev/ (covers symlinks to devices)
    if resolved.startswith("/dev/"):
        return True
    return False


def _parse_page_range(pages: str, total: int) -> tuple[int, int]:
    """Parse a page range like '2-5' into 0-based (start, end) inclusive."""
    parts = pages.strip().split("-")
    if len(parts) == 1:
        p = int(parts[0])
        return max(0, p - 1), min(p - 1, total - 1)
    start = int(parts[0])
    end = int(parts[1])
    return max(0, start - 1), min(end - 1, total - 1)


@tool_parameters(
    tool_parameters_schema(
        path=StringSchema("The file path to read"),
        offset=IntegerSchema(
            1,
            description="Line number to start reading from (1-indexed, default 1)",
            minimum=1,
        ),
        limit=IntegerSchema(
            2000,
            description="Maximum number of lines to read (default 2000)",
            minimum=1,
        ),
        pages=StringSchema("Page range for PDF files, e.g. '1-5' (default: all, max 20 pages)"),
        required=["path"],
    )
)
class ReadFileTool(_FsTool):
    """Read file contents with optional line-based pagination."""

    _MAX_CHARS = 128_000
    _DEFAULT_LIMIT = 2000
    _MAX_PDF_PAGES = 20

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "Read a file (text, image, or document). "
            "Text output format: LINE_NUM|CONTENT. "
            "Images return visual content for analysis. "
            "Supports PDF, DOCX, XLSX, PPTX documents. "
            "Use offset and limit for large text files. "
            "Reads exceeding ~128K chars are truncated."
        )

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, path: str | None = None, offset: int = 1, limit: int | None = None, pages: str | None = None, **kwargs: Any) -> Any:
        try:
            if not path:
                return "Error reading file: Unknown path"

            # Device path blacklist
            if _is_blocked_device(path):
                return f"Error: Reading {path} is blocked (device path that could hang or produce infinite output)."

            fp = self._resolve(path)
            if _is_blocked_device(fp):
                return f"Error: Reading {fp} is blocked (device path that could hang or produce infinite output)."
            if not fp.exists():
                return f"Error: File not found: {path}"
            if not fp.is_file():
                return f"Error: Not a file: {path}"

            # PDF support
            if fp.suffix.lower() == ".pdf":
                return self._read_pdf(fp, pages)

            # Office document support
            if fp.suffix.lower() in {".docx", ".xlsx", ".pptx"}:
                return self._read_office_doc(fp)

            raw = fp.read_bytes()
            if not raw:
                return f"(Empty file: {path})"

            mime = detect_image_mime(raw) or mimetypes.guess_type(path)[0]
            if mime and mime.startswith("image/"):
                return build_image_content_blocks(raw, mime, str(fp), f"(Image file: {path})")

            # Read dedup: same path + offset + limit + unchanged mtime → stub
            # Always check for external modifications before dedup
            entry = self._file_states.get(fp)
            try:
                current_mtime = os.path.getmtime(fp)
            except OSError:
                current_mtime = 0.0
            if entry and entry.can_dedup and entry.offset == offset and entry.limit == limit:
                if current_mtime != entry.mtime:
                    # File was modified externally - force full read and mark as not dedupable
                    entry.can_dedup = False
                    self._file_states.record_read(fp, offset=offset, limit=limit)  # Update state with new mtime
                    # Continue to read full content (don't return dedup message)
                else:
                    # File unchanged - return dedup message
                    # But only if content is actually unchanged (not just mtime)
                    current_hash = _hash_file(str(fp))
                    if current_hash == entry.content_hash:
                        return f"[File unchanged since last read: {path}]"
                    else:
                        # Content changed despite same mtime - force full read
                        entry.can_dedup = False
                        self._file_states.record_read(fp, offset=offset, limit=limit)
            else:
                # No previous state or marked as not dedupable - read full content
                self._file_states.record_read(fp, offset=offset, limit=limit)
                # Force full read by setting can_dedup to False for this read
                if entry:
                    entry.can_dedup = False

            # Read the file content after dedup check
            raw = fp.read_bytes()
            try:
                text_content = raw.decode("utf-8")
            except UnicodeDecodeError:
                # Binary file - return error message
                mime = detect_image_mime(raw) or mimetypes.guess_type(path)[0]
                if mime and mime.startswith("image/"):
                    return build_image_content_blocks(raw, mime, str(fp), f"(Image file: {path})")
                return f"Error: Cannot read binary file {path} (MIME: {mime or 'unknown'}). Only UTF-8 text and images are supported."

            # Normalize CRLF -> LF before line-splitting. Primarily a Windows
            # concern (git checkouts with autocrlf, editors saving CRLF) but
            # applied on all platforms so downstream StrReplace/Grep behavior
            # is consistent regardless of where the file was written.
            text_content = text_content.replace("\r\n", "\n")

            all_lines = text_content.splitlines()
            total = len(all_lines)

            if offset < 1:
                offset = 1
            if offset > total:
                return f"Error: offset {offset} is beyond end of file ({total} lines)"

            start = offset - 1
            end = min(start + (limit or self._DEFAULT_LIMIT), total)
            numbered = [f"{start + i + 1}| {line}" for i, line in enumerate(all_lines[start:end])]
            result = "\n".join(numbered)

            if len(result) > self._MAX_CHARS:
                trimmed, chars = [], 0
                for line in numbered:
                    chars += len(line) + 1
                    if chars > self._MAX_CHARS:
                        break
                    trimmed.append(line)
                end = start + len(trimmed)
                result = "\n".join(trimmed)

            if end < total:
                result += f"\n\n(Showing lines {offset}-{end} of {total}. Use offset={end + 1} to continue.)"
            else:
                result += f"\n\n(End of file — {total} lines total)"
            self._file_states.record_read(fp, offset=offset, limit=limit)
            return result
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error reading file: {e}"

    def _read_pdf(self, fp: Path, pages: str | None) -> str:
        try:
            import fitz  # pymupdf
        except ImportError:
            return "Error: PDF reading requires pymupdf. Install with: pip install pymupdf"

        try:
            doc = fitz.open(str(fp))
        except Exception as e:
            return f"Error reading PDF: {e}"

        total_pages = len(doc)
        if pages:
            try:
                start, end = _parse_page_range(pages, total_pages)
            except (ValueError, IndexError):
                doc.close()
                return f"Error: Invalid page range '{pages}'. Use format like '1-5'."
            if start > end or start >= total_pages:
                doc.close()
                return f"Error: Page range '{pages}' is out of bounds (document has {total_pages} pages)."
        else:
            start = 0
            end = min(total_pages - 1, self._MAX_PDF_PAGES - 1)

        if end - start + 1 > self._MAX_PDF_PAGES:
            end = start + self._MAX_PDF_PAGES - 1

        parts: list[str] = []
        for i in range(start, end + 1):
            page = doc[i]
            text = page.get_text().strip()
            if text:
                parts.append(f"--- Page {i + 1} ---\n{text}")
        doc.close()

        if not parts:
            return f"(PDF has no extractable text: {fp})"

        result = "\n\n".join(parts)
        if end < total_pages - 1:
            result += f"\n\n(Showing pages {start + 1}-{end + 1} of {total_pages}. Use pages='{end + 2}-{min(end + 1 + self._MAX_PDF_PAGES, total_pages)}' to continue.)"
        if len(result) > self._MAX_CHARS:
            result = result[:self._MAX_CHARS] + "\n\n(PDF text truncated at ~128K chars)"
        return result

    def _read_office_doc(self, fp: Path) -> str:
        from mlpcopilot.utils.document import extract_text

        result = extract_text(fp)

        if result is None:
            return f"Error: Unsupported file format: {fp.suffix}"

        if result.startswith("[error:"):
            return f"Error reading {fp.suffix.upper()} file: {result}"

        if not result:
            return f"({fp.suffix.upper().lstrip('.')} has no extractable text: {fp})"

        if len(result) > self._MAX_CHARS:
            result = result[:self._MAX_CHARS] + "\n\n(Document text truncated at ~128K chars)"

        return result


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------


@tool_parameters(
    tool_parameters_schema(
        path=StringSchema("The file or directory path to inspect"),
        required=["path"],
    )
)
class FileInfoTool(_FsTool):
    """Return read-only metadata for a file or directory."""

    read_only = True

    @property
    def name(self) -> str:
        return "file_info"

    @property
    def description(self) -> str:
        return (
            "Inspect file metadata without reading full contents or modifying anything. "
            "Always use this for file size, mtime, realpath, symlink targets, "
            "directory/file type, and binary/text checks. Do not use edit_file "
            "for metadata inspection."
        )

    async def execute(self, path: str | None = None, **kwargs: Any) -> str:
        try:
            if not path:
                raise ValueError("Unknown path")
            fp = self._resolve(path)
            exists = fp.exists()
            lines = [
                f"path: {path}",
                f"realpath: {fp}",
                f"exists: {str(exists).lower()}",
            ]
            if not exists:
                return "\n".join(lines)
            stat = fp.stat()
            size = stat.st_size
            lines.extend([
                f"type: {'directory' if fp.is_dir() else 'file' if fp.is_file() else 'other'}",
                f"size_bytes: {size}",
                f"size_human: {self._human_size(size)}",
                f"mtime: {stat.st_mtime:.6f}",
                f"suffix: {fp.suffix.lower()}",
            ])
            if fp.is_file():
                lines.append(f"binary_hint: {self._binary_hint(fp)}")
            return "\n".join(lines)
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error inspecting file: {e}"

    @staticmethod
    def _human_size(size: int) -> str:
        units = ("B", "KiB", "MiB", "GiB", "TiB")
        value = float(size)
        unit = units[0]
        for unit in units:
            if value < 1024 or unit == units[-1]:
                break
            value /= 1024
        return f"{int(value)} {unit}" if unit == "B" else f"{value:.2f} {unit}"

    @staticmethod
    def _binary_hint(path: Path) -> str:
        try:
            with path.open("rb") as handle:
                sample = handle.read(8192)
        except OSError:
            return "unknown"
        if b"\x00" in sample:
            return "binary"
        try:
            sample.decode("utf-8")
        except UnicodeDecodeError:
            return "binary"
        return "text"


@tool_parameters(
    tool_parameters_schema(
        path=StringSchema("The file path to write to"),
        content=StringSchema("The content to write"),
        approval_id=StringSchema("Approval ID for gated writes", nullable=True),
        required=["path", "content"],
    )
)
class WriteFileTool(_FsTool):
    """Write content to a file."""

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return (
            "Write content to a file. Overwrites if the file already exists; "
            "creates parent directories as needed. "
            "For partial edits, prefer edit_file instead."
        )

    async def execute(
        self,
        path: str | None = None,
        content: str | None = None,
        approval_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        try:
            if not path:
                raise ValueError("Unknown path")
            if content is None:
                raise ValueError("Unknown content")
            fp = self._resolve_write(path)
            protected_error = self._protected_runtime_write_error(fp)
            if protected_error:
                return protected_error
            allowlist_error = self._write_allowlist_error(fp)
            if allowlist_error:
                return allowlist_error
            approval_error = self._write_approval_error(
                tool_name=self.name,
                resolved=fp,
                approval_id=approval_id,
                overwrites_existing=fp.exists(),
            )
            if approval_error:
                return approval_error
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding="utf-8")
            self._file_states.record_write(fp)
            return f"Successfully wrote {len(content)} characters to {fp}"
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error writing file: {e}"


# ---------------------------------------------------------------------------
# edit_file
# ---------------------------------------------------------------------------

_QUOTE_TABLE = str.maketrans({
    "\u2018": "'", "\u2019": "'",  # curly single → straight
    "\u201c": '"', "\u201d": '"',  # curly double → straight
    "'": "'", '"': '"',            # identity (kept for completeness)
})


def _normalize_quotes(s: str) -> str:
    return s.translate(_QUOTE_TABLE)


def _curly_double_quotes(text: str) -> str:
    parts: list[str] = []
    opening = True
    for ch in text:
        if ch == '"':
            parts.append("\u201c" if opening else "\u201d")
            opening = not opening
        else:
            parts.append(ch)
    return "".join(parts)


def _curly_single_quotes(text: str) -> str:
    parts: list[str] = []
    opening = True
    for i, ch in enumerate(text):
        if ch != "'":
            parts.append(ch)
            continue
        prev_ch = text[i - 1] if i > 0 else ""
        next_ch = text[i + 1] if i + 1 < len(text) else ""
        if prev_ch.isalnum() and next_ch.isalnum():
            parts.append("\u2019")
            continue
        parts.append("\u2018" if opening else "\u2019")
        opening = not opening
    return "".join(parts)


def _preserve_quote_style(old_text: str, actual_text: str, new_text: str) -> str:
    """Preserve curly quote style when a quote-normalized fallback matched."""
    if _normalize_quotes(old_text.strip()) != _normalize_quotes(actual_text.strip()) or old_text == actual_text:
        return new_text

    styled = new_text
    if any(ch in actual_text for ch in ("\u201c", "\u201d")) and '"' in styled:
        styled = _curly_double_quotes(styled)
    if any(ch in actual_text for ch in ("\u2018", "\u2019")) and "'" in styled:
        styled = _curly_single_quotes(styled)
    return styled


def _leading_ws(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" \t"))]


def _reindent_like_match(old_text: str, actual_text: str, new_text: str) -> str:
    """Preserve the outer indentation from the actual matched block."""
    old_lines = old_text.split("\n")
    actual_lines = actual_text.split("\n")
    if len(old_lines) != len(actual_lines):
        return new_text

    comparable = [
        (old_line, actual_line)
        for old_line, actual_line in zip(old_lines, actual_lines)
        if old_line.strip() and actual_line.strip()
    ]
    if not comparable or any(
        _normalize_quotes(old_line.strip()) != _normalize_quotes(actual_line.strip())
        for old_line, actual_line in comparable
    ):
        return new_text

    old_ws = _leading_ws(comparable[0][0])
    actual_ws = _leading_ws(comparable[0][1])
    if actual_ws == old_ws:
        return new_text

    if old_ws:
        if not actual_ws.startswith(old_ws):
            return new_text
        delta = actual_ws[len(old_ws):]
    else:
        delta = actual_ws

    if not delta:
        return new_text

    return "\n".join((delta + line) if line else line for line in new_text.split("\n"))


@dataclass(slots=True)
class _MatchSpan:
    start: int
    end: int
    text: str
    line: int


def _find_exact_matches(content: str, old_text: str) -> list[_MatchSpan]:
    matches: list[_MatchSpan] = []
    start = 0
    while True:
        idx = content.find(old_text, start)
        if idx == -1:
            break
        matches.append(
            _MatchSpan(
                start=idx,
                end=idx + len(old_text),
                text=content[idx : idx + len(old_text)],
                line=content.count("\n", 0, idx) + 1,
            )
        )
        start = idx + max(1, len(old_text))
    return matches


def _find_trim_matches(content: str, old_text: str, *, normalize_quotes: bool = False) -> list[_MatchSpan]:
    old_lines = old_text.splitlines()
    if not old_lines:
        return []

    content_lines = content.splitlines()
    content_lines_keepends = content.splitlines(keepends=True)
    if len(content_lines) < len(old_lines):
        return []

    offsets: list[int] = []
    pos = 0
    for line in content_lines_keepends:
        offsets.append(pos)
        pos += len(line)
    offsets.append(pos)

    if normalize_quotes:
        stripped_old = [_normalize_quotes(line.strip()) for line in old_lines]
    else:
        stripped_old = [line.strip() for line in old_lines]

    matches: list[_MatchSpan] = []
    window_size = len(stripped_old)
    for i in range(len(content_lines) - window_size + 1):
        window = content_lines[i : i + window_size]
        if normalize_quotes:
            comparable = [_normalize_quotes(line.strip()) for line in window]
        else:
            comparable = [line.strip() for line in window]
        if comparable != stripped_old:
            continue

        start = offsets[i]
        end = offsets[i + window_size]
        if content_lines_keepends[i + window_size - 1].endswith("\n"):
            end -= 1
        matches.append(
            _MatchSpan(
                start=start,
                end=end,
                text=content[start:end],
                line=i + 1,
            )
        )
    return matches


def _find_quote_matches(content: str, old_text: str) -> list[_MatchSpan]:
    norm_content = _normalize_quotes(content)
    norm_old = _normalize_quotes(old_text)
    matches: list[_MatchSpan] = []
    start = 0
    while True:
        idx = norm_content.find(norm_old, start)
        if idx == -1:
            break
        matches.append(
            _MatchSpan(
                start=idx,
                end=idx + len(old_text),
                text=content[idx : idx + len(old_text)],
                line=content.count("\n", 0, idx) + 1,
            )
        )
        start = idx + max(1, len(norm_old))
    return matches


def _find_matches(content: str, old_text: str) -> list[_MatchSpan]:
    """Locate all matches using progressively looser strategies."""
    for matcher in (
        lambda: _find_exact_matches(content, old_text),
        lambda: _find_trim_matches(content, old_text),
        lambda: _find_trim_matches(content, old_text, normalize_quotes=True),
        lambda: _find_quote_matches(content, old_text),
    ):
        matches = matcher()
        if matches:
            return matches
    return []


def _find_match_line_numbers(content: str, old_text: str) -> list[int]:
    """Return 1-based starting line numbers for the current matching strategies."""
    return [match.line for match in _find_matches(content, old_text)]


def _collapse_internal_whitespace(text: str) -> str:
    return "\n".join(" ".join(line.split()) for line in text.splitlines())


def _diagnose_near_match(old_text: str, actual_text: str) -> list[str]:
    """Return actionable hints describing why text was close but not exact."""
    hints: list[str] = []

    if old_text.lower() == actual_text.lower() and old_text != actual_text:
        hints.append("letter case differs")
    if _collapse_internal_whitespace(old_text) == _collapse_internal_whitespace(actual_text) and old_text != actual_text:
        hints.append("whitespace differs")
    if old_text.rstrip("\n") == actual_text.rstrip("\n") and old_text != actual_text:
        hints.append("trailing newline differs")
    if _normalize_quotes(old_text) == _normalize_quotes(actual_text) and old_text != actual_text:
        hints.append("quote style differs")

    return hints


def _best_window(old_text: str, content: str) -> tuple[float, int, list[str], list[str]]:
    """Find the closest line-window match and return ratio/start/snippet/hints."""
    lines = content.splitlines(keepends=True)
    old_lines = old_text.splitlines(keepends=True)
    window = max(1, len(old_lines))

    best_ratio, best_start = -1.0, 0
    best_window_lines: list[str] = []

    for i in range(max(1, len(lines) - window + 1)):
        current = lines[i : i + window]
        ratio = difflib.SequenceMatcher(None, old_lines, current).ratio()
        if ratio > best_ratio:
            best_ratio, best_start = ratio, i
            best_window_lines = current

    actual_text = "".join(best_window_lines).replace("\r\n", "\n").rstrip("\n")
    hints = _diagnose_near_match(old_text.replace("\r\n", "\n").rstrip("\n"), actual_text)
    return best_ratio, best_start, best_window_lines, hints


def _find_match(content: str, old_text: str) -> tuple[str | None, int]:
    """Locate old_text in content with a multi-level fallback chain:

    1. Exact substring match
    2. Line-trimmed sliding window (handles indentation differences)
    3. Smart quote normalization (curly ↔ straight quotes)

    Both inputs should use LF line endings (caller normalises CRLF).
    Returns (matched_fragment, count) or (None, 0).
    """
    matches = _find_matches(content, old_text)
    if not matches:
        return None, 0
    return matches[0].text, len(matches)


@tool_parameters(
    tool_parameters_schema(
        path=StringSchema("The file path to edit"),
        old_text=StringSchema("The text to find and replace"),
        new_text=StringSchema("The text to replace with"),
        replace_all=BooleanSchema(description="Replace all occurrences (default false)"),
        approval_id=StringSchema("Approval ID for gated edits", nullable=True),
        required=["path", "old_text", "new_text"],
    )
)
class EditFileTool(_FsTool):
    """Edit a file by replacing text with fallback matching."""

    _MAX_EDIT_FILE_SIZE = 1024 * 1024 * 1024  # 1 GiB
    _MARKDOWN_EXTS = frozenset({".md", ".mdx", ".markdown"})

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return (
            "Edit a file by replacing old_text with new_text. "
            "Do not use this tool for read-only inspection, file metadata, realpath, "
            "mtime, symlink, binary checks, or file size checks; use file_info instead. "
            "Tolerates minor whitespace/indentation differences and curly/straight quote mismatches. "
            "If old_text matches multiple times, you must provide more context "
            "or set replace_all=true. Shows a diff of the closest match on failure."
        )

    @staticmethod
    def _strip_trailing_ws(text: str) -> str:
        """Strip trailing whitespace from each line."""
        return "\n".join(line.rstrip() for line in text.split("\n"))

    @staticmethod
    def _no_op_metadata(path: str, fp: Path) -> str:
        try:
            stat = fp.stat()
        except OSError as exc:
            return f"No edit performed. Could not stat {path}: {exc}"
        size = stat.st_size
        units = ("B", "KiB", "MiB", "GiB", "TiB")
        value = float(size)
        unit = units[0]
        for unit in units:
            if value < 1024 or unit == units[-1]:
                break
            value /= 1024
        display = f"{int(value)} {unit}" if unit == "B" else f"{value:.2f} {unit}"
        return f"No edit performed. File metadata for {path}: size={size} bytes ({display})."

    async def execute(
        self, path: str | None = None, old_text: str | None = None,
        new_text: str | None = None,
        replace_all: bool = False, approval_id: str | None = None, **kwargs: Any,
    ) -> str:
        try:
            if not path:
                raise ValueError("Unknown path")
            if old_text is None:
                raise ValueError("Unknown old_text")
            if new_text is None:
                raise ValueError("Unknown new_text")

            # .ipynb detection
            if path.endswith(".ipynb"):
                return "Error: This is a Jupyter notebook. Use the notebook_edit tool instead of edit_file."

            fp = self._resolve_write(path)
            protected_error = self._protected_runtime_write_error(fp)
            if protected_error:
                return protected_error
            allowlist_error = self._write_allowlist_error(fp)
            if allowlist_error:
                return allowlist_error

            # Create-file semantics: old_text='' + file doesn't exist → create
            if not fp.exists():
                if old_text == "":
                    approval_error = self._write_approval_error(
                        tool_name=self.name,
                        resolved=fp,
                        approval_id=approval_id,
                        overwrites_existing=False,
                    )
                    if approval_error:
                        return approval_error
                    fp.parent.mkdir(parents=True, exist_ok=True)
                    fp.write_text(new_text, encoding="utf-8")
                    self._file_states.record_write(fp)
                    return f"Successfully created {fp}"
                return self._file_not_found_msg(path, fp)

            if old_text == new_text:
                return self._no_op_metadata(path, fp)

            # File size protection
            try:
                fsize = fp.stat().st_size
            except OSError:
                fsize = 0
            if fsize > self._MAX_EDIT_FILE_SIZE:
                return f"Error: File too large to edit ({fsize / (1024**3):.1f} GiB). Maximum is 1 GiB."

            # Create-file: old_text='' but file exists and not empty → reject
            if old_text == "":
                if fsize > 0:
                    return f"Error: Cannot create file — {path} already exists and is not empty."
                approval_error = self._write_approval_error(
                    tool_name=self.name,
                    resolved=fp,
                    approval_id=approval_id,
                    overwrites_existing=True,
                )
                if approval_error:
                    return approval_error
                fp.write_text(new_text, encoding="utf-8")
                self._file_states.record_write(fp)
                return f"Successfully edited {fp}"

            try:
                with fp.open("rb") as handle:
                    sample = handle.read(8192)
                sample.decode("utf-8")
            except UnicodeDecodeError:
                return "Error: Binary files cannot be edited with edit_file."

            approval_error = self._write_approval_error(
                tool_name=self.name,
                resolved=fp,
                approval_id=approval_id,
                overwrites_existing=True,
            )
            if approval_error:
                return approval_error

            # Read-before-edit check
            warning = self._file_states.check_read(fp)

            raw = fp.read_bytes()
            uses_crlf = b"\r\n" in raw
            content = raw.decode("utf-8").replace("\r\n", "\n")
            norm_old = old_text.replace("\r\n", "\n")
            matches = _find_matches(content, norm_old)

            if not matches:
                return self._not_found_msg(old_text, content, path)
            count = len(matches)
            if count > 1 and not replace_all:
                line_numbers = [match.line for match in matches]
                preview = ", ".join(f"line {n}" for n in line_numbers[:3])
                if len(line_numbers) > 3:
                    preview += ", ..."
                location_hint = f" at {preview}" if preview else ""
                return (
                    f"Warning: old_text appears {count} times{location_hint}. "
                    "Provide more context to make it unique, or set replace_all=true."
                )

            norm_new = new_text.replace("\r\n", "\n")

            # Trailing whitespace stripping (skip markdown to preserve double-space line breaks)
            if fp.suffix.lower() not in self._MARKDOWN_EXTS:
                norm_new = self._strip_trailing_ws(norm_new)

            selected = matches if replace_all else matches[:1]
            new_content = content
            for match in reversed(selected):
                replacement = _preserve_quote_style(norm_old, match.text, norm_new)
                replacement = _reindent_like_match(norm_old, match.text, replacement)

                # Delete-line cleanup: when deleting text (new_text=''), consume trailing
                # newline to avoid leaving a blank line
                end = match.end
                if replacement == "" and not match.text.endswith("\n") and content[end:end + 1] == "\n":
                    end += 1

                new_content = new_content[: match.start] + replacement + new_content[end:]
            if uses_crlf:
                new_content = new_content.replace("\n", "\r\n")

            fp.write_bytes(new_content.encode("utf-8"))
            self._file_states.record_write(fp)
            msg = f"Successfully edited {fp}"
            if warning:
                msg = f"{warning}\n{msg}"
            return msg
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error editing file: {e}"

    def _file_not_found_msg(self, path: str, fp: Path) -> str:
        """Build an error message with 'Did you mean ...?' suggestions."""
        parent = fp.parent
        suggestions: list[str] = []
        if parent.is_dir():
            siblings = [f.name for f in parent.iterdir() if f.is_file()]
            close = difflib.get_close_matches(fp.name, siblings, n=3, cutoff=0.6)
            suggestions = [str(parent / c) for c in close]
        parts = [f"Error: File not found: {path}"]
        if suggestions:
            parts.append("Did you mean: " + ", ".join(suggestions) + "?")
        return "\n".join(parts)

    @staticmethod
    def _not_found_msg(old_text: str, content: str, path: str) -> str:
        best_ratio, best_start, best_window_lines, hints = _best_window(old_text, content)
        if best_ratio > 0.5:
            diff = "\n".join(difflib.unified_diff(
                old_text.splitlines(keepends=True),
                best_window_lines,
                fromfile="old_text (provided)",
                tofile=f"{path} (actual, line {best_start + 1})",
                lineterm="",
            ))
            hint_text = ""
            if hints:
                hint_text = "\nPossible cause: " + ", ".join(hints) + "."
            return (
                f"Error: old_text not found in {path}."
                f"{hint_text}\nBest match ({best_ratio:.0%} similar) at line {best_start + 1}:\n{diff}"
            )

        if hints:
            return (
                f"Error: old_text not found in {path}. "
                f"Possible cause: {', '.join(hints)}. "
                "Copy the exact text from read_file and try again."
            )
        return f"Error: old_text not found in {path}. No similar text found. Verify the file content."


# ---------------------------------------------------------------------------
# list_dir
# ---------------------------------------------------------------------------

@tool_parameters(
    tool_parameters_schema(
        path=StringSchema("The directory path to list"),
        recursive=BooleanSchema(description="Recursively list all files (default false)"),
        max_entries=IntegerSchema(
            200,
            description="Maximum entries to return (default 200)",
            minimum=1,
        ),
        required=["path"],
    )
)
class ListDirTool(_FsTool):
    """List directory contents with optional recursion."""

    _DEFAULT_MAX = 200
    _IGNORE_DIRS = {
        ".git", "node_modules", "__pycache__", ".venv", "venv",
        "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
        ".ruff_cache", ".coverage", "htmlcov",
    }

    @property
    def name(self) -> str:
        return "list_dir"

    @property
    def description(self) -> str:
        return (
            "List the contents of a directory. "
            "Set recursive=true to explore nested structure. "
            "Common noise directories (.git, node_modules, __pycache__, etc.) are auto-ignored."
        )

    @property
    def read_only(self) -> bool:
        return True

    async def execute(
        self, path: str | None = None, recursive: bool = False,
        max_entries: int | None = None, **kwargs: Any,
    ) -> str:
        try:
            if path is None:
                raise ValueError("Unknown path")
            dp = self._resolve(path)
            if not dp.exists():
                return f"Error: Directory not found: {path}"
            if not dp.is_dir():
                return f"Error: Not a directory: {path}"

            cap = max_entries or self._DEFAULT_MAX
            items: list[str] = []
            total = 0

            if recursive:
                for item in sorted(dp.rglob("*")):
                    if any(p in self._IGNORE_DIRS for p in item.parts):
                        continue
                    total += 1
                    if len(items) < cap:
                        rel = item.relative_to(dp)
                        items.append(f"{rel}/" if item.is_dir() else str(rel))
            else:
                for item in sorted(dp.iterdir()):
                    if item.name in self._IGNORE_DIRS:
                        continue
                    total += 1
                    if len(items) < cap:
                        pfx = "📁 " if item.is_dir() else "📄 "
                        items.append(f"{pfx}{item.name}")

            if not items and total == 0:
                return f"Directory {path} is empty"

            result = "\n".join(items)
            if total > cap:
                result += f"\n\n(truncated, showing first {cap} of {total} entries)"
            return result
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error listing directory: {e}"
