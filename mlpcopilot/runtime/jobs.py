"""Persistent background job records for MLP Copilot runtime."""

from __future__ import annotations

import json
import os
import signal
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class JobRecord:
    job_id: str
    kind: str
    command: str
    status: str
    pid: int | None = None
    process_group: int | None = None
    started_at: str = ""
    ended_at: str | None = None
    cwd: str = ""
    log_path: str = ""
    returncode: int | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "kind": self.kind,
            "command": self.command,
            "status": self.status,
            "pid": self.pid,
            "process_group": self.process_group,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "cwd": self.cwd,
            "log_path": self.log_path,
            "returncode": self.returncode,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobRecord":
        return cls(
            job_id=str(data.get("job_id") or ""),
            kind=str(data.get("kind") or "job"),
            command=str(data.get("command") or ""),
            status=str(data.get("status") or "unknown"),
            pid=_int_or_none(data.get("pid")),
            process_group=_int_or_none(data.get("process_group")),
            started_at=str(data.get("started_at") or ""),
            ended_at=str(data.get("ended_at")) if data.get("ended_at") is not None else None,
            cwd=str(data.get("cwd") or ""),
            log_path=str(data.get("log_path") or ""),
            returncode=_int_or_none(data.get("returncode")),
            error=str(data.get("error")) if data.get("error") is not None else None,
        )


class JobStore:
    """Append-only jobs.jsonl store with latest-record collapse on read."""

    def __init__(self, workspace: Path | str):
        self.workspace = Path(workspace).expanduser()
        self.jobs_dir = self.workspace / "jobs"
        self.jobs_path = self.jobs_dir / "jobs.jsonl"

    def record_start(
        self,
        *,
        kind: str,
        command: str,
        pid: int | None,
        job_id: str | None = None,
        process_group: int | None = None,
        cwd: str = "",
        log_path: Path | str | None = None,
    ) -> JobRecord:
        job_id = job_id or f"{kind}_{os.getpid()}_{int(time.time() * 1000)}"
        record = JobRecord(
            job_id=job_id,
            kind=kind,
            command=command,
            status="running",
            pid=pid,
            process_group=process_group,
            started_at=_now_iso(),
            cwd=cwd,
            log_path=self._display_path(log_path) if log_path is not None else "",
        )
        self._append(record)
        return record

    def update(
        self,
        job_id: str,
        *,
        status: str,
        returncode: int | None = None,
        error: str | None = None,
    ) -> JobRecord | None:
        record = self.get(job_id)
        if record is None:
            return None
        record.status = status
        record.ended_at = _now_iso()
        record.returncode = returncode
        record.error = error
        self._append(record)
        return record

    def set_log_path(self, job_id: str, log_path: Path | str) -> JobRecord | None:
        record = self.get(job_id)
        if record is None:
            return None
        record.log_path = self._display_path(log_path)
        self._append(record)
        return record

    def stop(self, job_id: str) -> tuple[JobRecord | None, str]:
        record = self.get(job_id)
        if record is None:
            return None, f"Job not found: {job_id}"
        if record.status != "running":
            return record, f"Job {job_id} is already {record.status}."
        target = record.process_group or record.pid
        if target is None:
            updated = self.update(job_id, status="failed", error="missing pid")
            return updated or record, f"Job {job_id} has no pid; marked failed."
        try:
            kill_group = getattr(os, "killpg", None)
            if callable(kill_group):
                kill_group(target, signal.SIGTERM)
            else:
                os.kill(target, signal.SIGTERM)
        except ProcessLookupError:
            updated = self.update(job_id, status="exited")
            return updated or record, f"Job {job_id} was not running; marked exited."
        except PermissionError as exc:
            updated = self.update(job_id, status="failed", error=str(exc))
            return updated or record, f"Could not stop job {job_id}: {exc}"
        updated = self.update(job_id, status="stopped")
        return updated or record, f"Stopped job {job_id}."

    def finish(self, job_id: str, *, returncode: int) -> JobRecord | None:
        record = self.get(job_id)
        if record is None:
            return None
        status = record.status
        if status != "stopped":
            status = "exited" if returncode == 0 else "failed"
        return self.update(job_id, status=status, returncode=returncode)

    def get(self, job_id: str) -> JobRecord | None:
        for record in self.list_jobs(limit=None):
            if record.job_id == job_id:
                return record
        return None

    def list_jobs(self, *, limit: int | None = 20, reconcile: bool = True) -> list[JobRecord]:
        records = self._load_latest()
        if reconcile:
            records = self._reconcile(records)
        ordered = sorted(records.values(), key=lambda item: item.started_at, reverse=True)
        return ordered if limit is None else ordered[:limit]

    def reconcile_stale(self, *, mark_missing_pid: bool = False) -> list[JobRecord]:
        """Persist status updates for stale running jobs and return changed records."""
        records = self._load_latest()
        changed: list[JobRecord] = []
        for record in records.values():
            if self._reconcile_record(record, mark_missing_pid=mark_missing_pid):
                self._append(record)
                changed.append(record)
        return changed

    def _load_latest(self) -> dict[str, JobRecord]:
        latest: dict[str, JobRecord] = {}
        if not self.jobs_path.exists():
            return latest
        for line in self.jobs_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            record = JobRecord.from_dict(data)
            if record.job_id:
                latest[record.job_id] = record
        return latest

    def _append(self, record: JobRecord) -> None:
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        with self.jobs_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

    def _display_path(self, path: Path | str) -> str:
        resolved = Path(path).expanduser()
        try:
            return str(resolved.relative_to(self.workspace))
        except ValueError:
            return str(resolved)

    def _reconcile(self, records: dict[str, JobRecord]) -> dict[str, JobRecord]:
        for record in list(records.values()):
            if self._reconcile_record(record, mark_missing_pid=False):
                self._append(record)
        return records

    def _reconcile_record(self, record: JobRecord, *, mark_missing_pid: bool) -> bool:
        if record.status != "running":
            return False
        if record.pid is None:
            if not mark_missing_pid:
                return False
            record.status = "failed"
            record.ended_at = _now_iso()
            record.error = record.error or "missing pid during startup reconcile"
            return True
        if _pid_exists(record.pid):
            return False
        record.status = "exited"
        record.ended_at = _now_iso()
        return True


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None
