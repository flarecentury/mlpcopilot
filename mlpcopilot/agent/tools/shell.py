"""Shell execution tool."""

import asyncio
import os
import re
import shlex
import shutil
import signal
import sys
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from loguru import logger

from mlpcopilot.agent.tools.base import Tool, tool_parameters
from mlpcopilot.agent.tools.sandbox import wrap_command
from mlpcopilot.agent.tools.schema import (
    BooleanSchema,
    IntegerSchema,
    StringSchema,
    tool_parameters_schema,
)
from mlpcopilot.config.paths import get_media_dir
from mlpcopilot.runtime.jobs import JobStore

_IS_WINDOWS = sys.platform == "win32"
_DEFAULT_BACKGROUND_COMMANDS = (
    "cmatrix",
    "top",
    "htop",
    "btop",
    "watch",
)
_DEFAULT_DENY_PATTERNS = (
    r"\brm\s+(?:-[^\s]*r[^\s]*f|-[^\s]*f[^\s]*r|-[^\s]*r\b.*\s-[^\s]*f\b|-[^\s]*f\b.*\s-[^\s]*r\b)\s+(?:/|~|[a-z]:\\)",
)


@tool_parameters(
    tool_parameters_schema(
        command=StringSchema("The shell command to execute"),
        working_dir=StringSchema("Optional working directory for the command"),
        approval_id=StringSchema("Approval ID for approval-gated command execution", nullable=True),
        timeout=IntegerSchema(
            60,
            description=(
                "Timeout in seconds. Increase for long-running commands "
                "like compilation or installation (default 60, max 600)."
            ),
            minimum=1,
            maximum=600,
        ),
        background=BooleanSchema(
            description=(
                "Run a long-lived or interactive command in the background and return immediately. "
                "Use for servers, monitors, training jobs, cmatrix/top/htop, or other commands whose "
                "live output is not needed in the chat response."
            ),
            default=False,
            nullable=True,
        ),
        required=["command"],
    )
)
class ExecTool(Tool):
    """Tool to execute shell commands."""

    def __init__(
        self,
        timeout: int = 60,
        working_dir: str | None = None,
        deny_patterns: list[str] | None = None,
        allow_commands: list[str] | None = None,
        readonly_commands: list[str] | None = None,
        background_commands: list[str] | None = None,
        allow_patterns: list[str] | None = None,
        require_allowlist: bool = False,
        approval_required: bool = False,
        restrict_to_workspace: bool = False,
        sandbox: str = "",
        path_append: str = "",
        allowed_env_keys: list[str] | None = None,
    ):
        self.timeout = timeout
        self.working_dir = working_dir
        self.sandbox = sandbox
        self._extra_deny_patterns = list(deny_patterns or [])
        self.deny_patterns = [*_DEFAULT_DENY_PATTERNS, *self._extra_deny_patterns]
        self.allow_commands = [cmd.strip() for cmd in (allow_commands or []) if cmd.strip()]
        self.readonly_commands = {
            cmd.strip() for cmd in (readonly_commands or []) if cmd.strip()
        }
        configured_background_commands = (
            _DEFAULT_BACKGROUND_COMMANDS if background_commands is None else background_commands
        )
        self.background_commands = {
            cmd.strip() for cmd in configured_background_commands if cmd.strip()
        }
        self.allow_patterns = allow_patterns or []
        self.require_allowlist = require_allowlist
        self.approval_required = approval_required
        self.restrict_to_workspace = restrict_to_workspace
        self.path_append = path_append
        self.allowed_env_keys = allowed_env_keys or []
        self._background_reapers: set[asyncio.Task] = set()

    @property
    def name(self) -> str:
        return "exec"

    _MAX_TIMEOUT = 600
    _MAX_OUTPUT = 10_000
    _MAX_OUTPUT_PREVIEW = 4_000

    @property
    def description(self) -> str:
        return (
            "Execute a shell command and return its output. "
            "Prefer read_file/write_file/edit_file over cat/echo/sed, "
            "and grep/glob over shell find/grep. "
            "Use -y or --yes flags to avoid interactive prompts. "
            "Large output is written to a jobs log and previewed in chat; "
            "timeout defaults to 60s."
        )

    @property
    def exclusive(self) -> bool:
        return True

    async def execute(
        self, command: str, working_dir: str | None = None,
        timeout: int | None = None, approval_id: str | None = None,
        background: bool | None = None, **kwargs: Any,
    ) -> str:
        cwd = working_dir or self.working_dir or os.getcwd()

        # Prevent an LLM-supplied working_dir from escaping the configured
        # workspace when restrict_to_workspace is enabled (#2826). Without
        # this, a caller can pass working_dir="/etc" and then all absolute
        # paths under /etc would pass the _guard_command check that anchors
        # on cwd.
        if self.restrict_to_workspace and self.working_dir:
            try:
                requested = Path(cwd).expanduser().resolve()
                workspace_root = Path(self.working_dir).expanduser().resolve()
            except Exception:
                return "Error: working_dir could not be resolved"
            if requested != workspace_root and workspace_root not in requested.parents:
                return "Error: working_dir is outside the configured workspace"

        guard_error = self._guard_command(command, cwd)
        if guard_error:
            return guard_error

        approval_error = self._approval_error(command, cwd, approval_id, background=background)
        if approval_error:
            return approval_error

        if self.sandbox:
            if _IS_WINDOWS:
                logger.warning(
                    "Sandbox '{}' is not supported on Windows; running unsandboxed",
                    self.sandbox,
                )
            else:
                workspace = self.working_dir or cwd
                command = wrap_command(self.sandbox, command, workspace, cwd)
                cwd = str(Path(workspace).resolve())

        effective_timeout = min(timeout or self.timeout, self._MAX_TIMEOUT)
        env = self._build_env()

        if self.path_append:
            if _IS_WINDOWS:
                env["PATH"] = env.get("PATH", "") + os.pathsep + self.path_append
            else:
                env["MLPCOPILOT_PATH_APPEND"] = self.path_append
                command = f'export PATH="$PATH{os.pathsep}$MLPCOPILOT_PATH_APPEND"; {command}'

        if self._should_run_background(command, background):
            return await self._start_background(command, cwd, env)

        try:
            process = await self._spawn(command, cwd, env)
            pid = self._process_pid(process)
            foreground_job_id = self._record_foreground_start(
                command=command,
                cwd=cwd,
                pid=pid,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=effective_timeout,
                )
            except asyncio.TimeoutError:
                await self._kill_process(process)
                self._finish_foreground_job(
                    foreground_job_id,
                    cwd=cwd,
                    returncode=process.returncode if process.returncode is not None else -9,
                )
                return f"Error: Command timed out after {effective_timeout} seconds"
            except asyncio.CancelledError:
                await self._kill_process(process)
                self._finish_foreground_job(
                    foreground_job_id,
                    cwd=cwd,
                    returncode=process.returncode if process.returncode is not None else -9,
                )
                raise

            output_parts = []

            if stdout:
                output_parts.append(stdout.decode("utf-8", errors="replace"))

            if stderr:
                stderr_text = stderr.decode("utf-8", errors="replace")
                if stderr_text.strip():
                    output_parts.append(f"STDERR:\n{stderr_text}")

            output_parts.append(f"\nExit code: {process.returncode}")

            result = "\n".join(output_parts) if output_parts else "(no output)"

            max_len = self._MAX_OUTPUT
            if len(result) > max_len:
                return self._format_large_output_result(
                    command=command,
                    cwd=cwd,
                    result=result,
                    returncode=process.returncode if process.returncode is not None else -1,
                    pid=pid,
                    job_id=foreground_job_id,
                )

            self._finish_foreground_job(
                foreground_job_id,
                cwd=cwd,
                returncode=process.returncode if process.returncode is not None else -1,
            )
            return result

        except Exception as e:
            return f"Error executing command: {str(e)}"

    async def _start_background(self, command: str, cwd: str, env: dict[str, str]) -> str:
        if _IS_WINDOWS:
            return "Error: background exec is not supported on Windows yet"
        workspace = Path(self.working_dir or cwd).expanduser()
        jobs_dir = workspace / "jobs"
        store = JobStore(workspace)
        try:
            jobs_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return f"Error: background exec log directory could not be created: {exc}"
        job_id = f"exec_{os.getpid()}_{int(asyncio.get_running_loop().time() * 1000)}"
        log_path = jobs_dir / f"{job_id}.log"
        bash = shutil.which("bash") or "/bin/bash"
        try:
            with log_path.open("ab", buffering=0) as log_file:
                process = await asyncio.create_subprocess_exec(
                    bash, "-l", "-c", command,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=log_file,
                    stderr=asyncio.subprocess.STDOUT,
                    cwd=cwd,
                    env=env,
                    start_new_session=True,
                )
        except Exception as exc:
            return f"Error starting background exec: {exc}"
        try:
            store.record_start(
                kind="exec",
                command=command,
                pid=process.pid,
                job_id=job_id,
                process_group=process.pid,
                cwd=cwd,
                log_path=log_path,
            )
        except OSError as exc:
            logger.warning("Could not record background exec job {}: {}", job_id, exc)
        task = asyncio.create_task(self._reap_background(process, log_path, store, job_id))
        self._background_reapers.add(task)
        task.add_done_callback(self._background_reapers.discard)
        return (
            "Background exec started.\n"
            f"Job: {job_id}\n"
            f"Command: {command}\n"
            f"PID: {process.pid}\n"
            f"Process group: {process.pid}\n"
            f"Log: {log_path}\n"
            f"Stop: kill -TERM -{process.pid}"
        )

    @staticmethod
    async def _reap_background(
        process: asyncio.subprocess.Process,
        log_path: Path,
        store: JobStore,
        job_id: str,
    ) -> None:
        returncode = await process.wait()
        with suppress(OSError):
            store.finish(job_id, returncode=returncode)
        with suppress(OSError):
            with log_path.open("ab") as f:
                f.write(f"\n[mlpcopilot] background exec exited with code {returncode}\n".encode())

    def _format_large_output_result(
        self,
        *,
        command: str,
        cwd: str,
        result: str,
        returncode: int,
        pid: int | None,
        job_id: str | None,
    ) -> str:
        log_path = self._write_foreground_output_log(job_id, cwd, result)
        self._finish_foreground_job(job_id, cwd=cwd, returncode=returncode)
        preview_len = min(self._MAX_OUTPUT_PREVIEW, self._MAX_OUTPUT)
        half = preview_len // 2
        omitted = max(0, len(result) - preview_len)
        marker = f"\n\n... ({omitted:,} chars truncated"
        if log_path:
            marker += f"; full output written to {log_path}"
        marker += ") ...\n\n"
        preview = result[:half] + marker + result[-half:]
        if log_path:
            return (
                f"Output exceeded {self._MAX_OUTPUT:,} chars. "
                f"Full output: {log_path}\n\n"
                f"{preview}"
            )
        return (
            f"Output exceeded {self._MAX_OUTPUT:,} chars. "
            "Full output could not be written; returning preview only.\n\n"
            f"{preview}"
        )

    def _record_foreground_start(
        self,
        *,
        command: str,
        cwd: str,
        pid: int | None,
    ) -> str | None:
        workspace = Path(self.working_dir or cwd).expanduser()
        store = JobStore(workspace)
        job_id = f"exec_{os.getpid()}_{time.time_ns()}"
        try:
            store.record_start(
                kind="exec",
                command=command,
                pid=pid,
                job_id=job_id,
                process_group=pid if not _IS_WINDOWS else None,
                cwd=cwd,
            )
            return job_id
        except OSError as exc:
            logger.warning("Could not record foreground exec job {}: {}", job_id, exc)
            return None

    def _write_foreground_output_log(
        self,
        job_id: str | None,
        cwd: str,
        result: str,
    ) -> str | None:
        if not job_id:
            return None
        workspace = Path(self.working_dir or cwd).expanduser()
        jobs_dir = workspace / "jobs"
        log_path = jobs_dir / f"{job_id}.log"
        try:
            jobs_dir.mkdir(parents=True, exist_ok=True)
            log_path.write_text(result, encoding="utf-8", errors="replace")
            record = JobStore(workspace).set_log_path(job_id, log_path)
            return record.log_path if record is not None else str(log_path)
        except OSError as exc:
            logger.warning("Could not record large exec output {}: {}", job_id, exc)
            return None

    def _finish_foreground_job(self, job_id: str | None, *, cwd: str, returncode: int) -> None:
        if not job_id:
            return
        workspace = Path(self.working_dir or cwd).expanduser()
        with suppress(OSError):
            JobStore(workspace).finish(job_id, returncode=returncode)

    @staticmethod
    def _process_pid(process: Any) -> int | None:
        pid = getattr(process, "pid", None)
        return pid if isinstance(pid, int) and not isinstance(pid, bool) else None

    @staticmethod
    async def _spawn(
        command: str, cwd: str, env: dict[str, str],
    ) -> asyncio.subprocess.Process:
        """Launch *command* in a platform-appropriate shell."""
        if _IS_WINDOWS:
            comspec = env.get("COMSPEC", os.environ.get("COMSPEC", "cmd.exe"))
            return await asyncio.create_subprocess_exec(
                comspec, "/c", command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )
        bash = shutil.which("bash") or "/bin/bash"
        return await asyncio.create_subprocess_exec(
            bash, "-l", "-c", command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
            start_new_session=True,
        )

    @staticmethod
    async def _kill_process(process: asyncio.subprocess.Process) -> None:
        """Kill a subprocess and reap it to prevent zombies."""
        if _IS_WINDOWS:
            process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(process.wait(), timeout=5.0)
        finally:
            if not _IS_WINDOWS:
                try:
                    os.waitpid(process.pid, os.WNOHANG)
                except (ProcessLookupError, ChildProcessError) as e:
                    logger.debug("Process already reaped or not found: {}", e)

    def _build_env(self) -> dict[str, str]:
        """Build a minimal environment for subprocess execution.

        On Unix, only HOME/LANG/TERM are passed; ``bash -l`` sources the
        user's profile which sets PATH and other essentials.

        On Windows, ``cmd.exe`` has no login-profile mechanism, so a curated
        set of system variables (including PATH) is forwarded.  API keys and
        other secrets are still excluded.
        """
        if _IS_WINDOWS:
            sr = os.environ.get("SYSTEMROOT", r"C:\Windows")
            env = {
                "SYSTEMROOT": sr,
                "COMSPEC": os.environ.get("COMSPEC", f"{sr}\\system32\\cmd.exe"),
                "USERPROFILE": os.environ.get("USERPROFILE", ""),
                "HOMEDRIVE": os.environ.get("HOMEDRIVE", "C:"),
                "HOMEPATH": os.environ.get("HOMEPATH", "\\"),
                "TEMP": os.environ.get("TEMP", f"{sr}\\Temp"),
                "TMP": os.environ.get("TMP", f"{sr}\\Temp"),
                "PATHEXT": os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD"),
                "PATH": os.environ.get("PATH", f"{sr}\\system32;{sr}"),
                "APPDATA": os.environ.get("APPDATA", ""),
                "LOCALAPPDATA": os.environ.get("LOCALAPPDATA", ""),
                "ProgramData": os.environ.get("ProgramData", ""),
                "ProgramFiles": os.environ.get("ProgramFiles", ""),
                "ProgramFiles(x86)": os.environ.get("ProgramFiles(x86)", ""),
                "ProgramW6432": os.environ.get("ProgramW6432", ""),
            }
            for key in self.allowed_env_keys:
                val = os.environ.get(key)
                if val is not None:
                    env[key] = val
            return env
        home = os.environ.get("HOME", "/tmp")
        env = {
            "HOME": home,
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "TERM": os.environ.get("TERM", "dumb"),
        }
        for key in self.allowed_env_keys:
            val = os.environ.get(key)
            if val is not None:
                env[key] = val
        return env

    def _guard_command(self, command: str, cwd: str) -> str | None:
        """Enforce configured allowlist, workspace, and network boundaries."""
        cmd = command.strip()
        lower = cmd.lower()

        if self.allow_patterns and any(re.search(pattern, lower) for pattern in self.allow_patterns):
            return None

        hard_deny_patterns = (
            self._extra_deny_patterns
            if self.approval_required
            else self.deny_patterns
        )
        for pattern in hard_deny_patterns:
            if re.search(pattern, lower):
                return "Error: Command blocked by safety guard (deny pattern filter)"

        has_allowlist = bool(self.allow_commands or self.readonly_commands or self.allow_patterns)
        if self.require_allowlist and not has_allowlist and not self.approval_required:
            return "Error: Command blocked by safety guard (exec allowlist is empty)"

        if has_allowlist and not self._is_allowlisted_command(cmd, lower):
            if self.approval_required:
                return None
            return "Error: Command blocked by safety guard (not in allowlist)"

        from mlpcopilot.security.network import contains_internal_url
        if contains_internal_url(cmd):
            return "Error: Command blocked by safety guard (internal/private URL detected)"

        if self.restrict_to_workspace:
            if "..\\" in cmd or "../" in cmd:
                return "Error: Command blocked by safety guard (path traversal detected)"

            cwd_path = Path(cwd).resolve()

            for raw in self._extract_absolute_paths(cmd):
                try:
                    expanded = os.path.expandvars(raw.strip())
                    p = Path(expanded).expanduser().resolve()
                except Exception:
                    continue

                media_path = get_media_dir().resolve()
                if (p.is_absolute()
                    and p != Path("/dev/null")
                    and cwd_path not in p.parents
                    and p != cwd_path
                    and media_path not in p.parents
                    and p != media_path
                ):
                    return "Error: Command blocked by safety guard (path outside working dir)"

        return None

    def _approval_error(
        self,
        command: str,
        cwd: str,
        approval_id: str | None,
        *,
        background: bool | None = None,
    ) -> str | None:
        if not self.approval_required:
            return None

        workspace = self.working_dir
        if not workspace:
            return "Error: Command approval requires a configured workspace"

        from mlpcopilot.agent.tools.session_context import current_session_key
        from mlpcopilot.runtime.approval import ApprovalManager

        normalized_command = command.strip()
        if self._approval_exempt_command(normalized_command):
            return None

        normalized_cwd = str(Path(cwd).expanduser().resolve())
        session_key = current_session_key()
        manager = ApprovalManager(Path(workspace), session_key=session_key)

        if approval_id:
            record = manager.get(approval_id)
            if record is None:
                return f"Error: Approval not found: {approval_id}"
            if record.status not in {"approved", "partially_approved"}:
                return f"Error: Approval {approval_id} is {record.status}; command blocked."
            metadata = record.metadata or {}
            expected_command = metadata.get("command")
            expected_cwd = metadata.get("working_dir")
            if expected_command and expected_command != normalized_command:
                return (
                    f"Error: Approval {approval_id} is for a different command; "
                    "command blocked."
                )
            if expected_cwd and expected_cwd != normalized_cwd:
                return (
                    f"Error: Approval {approval_id} is for working_dir {expected_cwd}, "
                    f"not {normalized_cwd}; command blocked."
                )
            return None

        record = self._find_pending_exec_approval(manager, normalized_command, normalized_cwd)
        if record is None:
            arguments = {"command": normalized_command, "working_dir": normalized_cwd}
            if background is not None:
                arguments["background"] = bool(background)
            record = manager.create(
                action_type="exec_command",
                title=f"Approve exec: {normalized_command[:80]}",
                request=(
                    "exec wants to run a shell command.\n\n"
                    f"Command: {normalized_command}\n"
                    f"Working directory: {normalized_cwd}"
                ),
                requester="agent",
                metadata={
                    "tool": "exec",
                    "arguments": arguments,
                    "command": normalized_command,
                    "working_dir": normalized_cwd,
                    "background": bool(background) if background is not None else None,
                    **({"session_key": session_key} if session_key else {}),
                },
            )
        if session_key:
            return (
                "Error: Approval required before executing command. "
                f"Approval ID: {record.approval_id}. "
                f"Approve in this TUI session with /approve {record.approval_id}."
            )
        return (
            "Error: Approval required before executing command. "
            f"Approval ID: {record.approval_id}. "
            f"Approve with /approve {record.approval_id} or "
            f"mlpcopilot mlp approve {record.approval_id}."
        )

    @staticmethod
    def _find_pending_exec_approval(
        manager: Any,
        command: str,
        working_dir: str,
    ) -> Any | None:
        for record in manager.list_pending():
            metadata = record.metadata or {}
            if (
                record.action_type in {"exec_command", "destructive_exec"}
                and metadata.get("tool") == "exec"
                and metadata.get("command") == command
                and metadata.get("working_dir") == working_dir
            ):
                return record
            if (
                record.action_type == "tool_execution"
                and metadata.get("tool") == "exec"
                and metadata.get("command") == command
                and (
                    not isinstance(metadata.get("working_dir"), str)
                    or metadata.get("working_dir") == working_dir
                )
            ):
                return record
        return None

    @staticmethod
    def _extract_absolute_paths(command: str) -> list[str]:
        # Windows: match drive-root paths like `C:\` as well as `C:\path\to\file`
        # NOTE: `*` is required so `C:\` (nothing after the slash) is still extracted.
        win_paths = re.findall(r"[A-Za-z]:\\[^\s\"'|><;]*", command)
        posix_paths = re.findall(r"(?:^|[\s|>'\"])(/[^\s\"'>;|<]+)", command) # POSIX: /absolute only
        home_paths = re.findall(r"(?:^|[\s|>'\"])(~[^\s\"'>;|<]*)", command) # POSIX/Windows home shortcut: ~
        return win_paths + posix_paths + home_paths

    def _is_allowlisted_command(self, command: str, lower_command: str | None = None) -> bool:
        return self._is_exact_allowed_command(command) or any(
            re.search(pattern, lower_command or command.lower())
            for pattern in self.allow_patterns
        ) or self._is_readonly_allowed_command(command)

    def _is_exact_allowed_command(self, command: str) -> bool:
        return command.strip() in self.allow_commands

    def _approval_exempt_command(self, command: str) -> bool:
        return self._is_exact_allowed_command(command) or self._is_readonly_allowed_command(command)

    def _is_readonly_allowed_command(self, command: str) -> bool:
        cmd = command.strip()
        if not cmd or _IS_WINDOWS:
            return False
        try:
            segments = self._split_readonly_command_chain(cmd)
        except ValueError:
            return False
        if not segments:
            return False
        for idx, segment in enumerate(segments):
            if self._is_readonly_simple_command(segment):
                continue
            if self._is_safe_echo_fallback(segment, idx=idx, total=len(segments)):
                continue
            return False
        return True

    def _split_readonly_command_chain(self, command: str) -> list[list[str]]:
        if any(marker in command for marker in ("`", "$(", "\n", "\r", ";")):
            return []
        argv = shlex.split(command, posix=True)
        if not argv:
            return []
        segments: list[list[str]] = []
        current: list[str] = []
        expect_command = True
        idx = 0
        while idx < len(argv):
            token = argv[idx]
            if token in {"&&", "||"}:
                if expect_command or not current:
                    return []
                segments.append(current)
                current = []
                expect_command = True
                idx += 1
                continue
            if token in {"|", "&"}:
                return []
            if self._is_safe_devnull_redirect_token(token):
                idx += 1
                continue
            if token in {">", "1>", "2>", ">>", "1>>", "2>>"}:
                if idx + 1 >= len(argv) or argv[idx + 1] != "/dev/null":
                    return []
                idx += 2
                continue
            if ">" in token or "<" in token:
                return []
            current.append(token)
            expect_command = False
            idx += 1
        if expect_command or not current:
            return []
        segments.append(current)
        return segments

    @staticmethod
    def _is_safe_devnull_redirect_token(token: str) -> bool:
        return bool(re.fullmatch(r"(?:[012])?>?>/dev/null", token))

    def _is_readonly_simple_command(self, argv: list[str]) -> bool:
        if not argv:
            return False
        executable = Path(argv[0]).name
        return executable in self.readonly_commands

    @staticmethod
    def _is_safe_echo_fallback(argv: list[str], *, idx: int, total: int) -> bool:
        if idx == 0 or idx != total - 1:
            return False
        if not argv or Path(argv[0]).name != "echo":
            return False
        return all(not token.startswith("-") for token in argv[1:])

    def _should_run_background(self, command: str, background: bool | None) -> bool:
        if background is not None:
            return bool(background)
        cmd = command.strip()
        if not cmd or _IS_WINDOWS or self._has_shell_mutation_syntax(cmd):
            return False
        try:
            argv = shlex.split(cmd, posix=True)
        except ValueError:
            return False
        if not argv:
            return False
        return Path(argv[0]).name in self.background_commands

    @staticmethod
    def _has_shell_mutation_syntax(command: str) -> bool:
        return bool(re.search(r"[|&;<>`]", command) or "$(" in command or "\n" in command or "\r" in command)
