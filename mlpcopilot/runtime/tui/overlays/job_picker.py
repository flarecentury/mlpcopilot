"""Background job picker overlay rendering."""

from __future__ import annotations

from mlpcopilot.runtime.jobs import JobRecord, JobStore
from mlpcopilot.runtime.tui.common import _short
from mlpcopilot.runtime.tui.state import RuntimeTuiState


def job_picker_jobs(workspace: str | object, *, limit: int = 50) -> list[JobRecord]:
    """Return recent jobs for the picker."""
    return JobStore(workspace).list_jobs(limit=limit)


def selected_job(state: RuntimeTuiState, jobs: list[JobRecord]) -> JobRecord | None:
    if not jobs:
        return None
    state.job_picker_selection %= len(jobs)
    return jobs[state.job_picker_selection]


def _render_job_picker_ansi(
    state: RuntimeTuiState,
    jobs: list[JobRecord],
    *,
    width: int,
    height: int,
) -> str:
    if not jobs:
        return "Jobs: none.\n\nEsc closes this picker."
    state.job_picker_selection %= len(jobs)
    rows = max(1, height - 4)
    selected = state.job_picker_selection
    start = min(max(0, selected - rows + 1), max(0, len(jobs) - rows))
    visible = jobs[start:start + rows]
    header = "jobs | Up/Down select | Enter stop running job | Esc close"
    divider = "-" * min(width, max(8, len(header)))
    lines = [header, divider, "State     Kind  Job / Command"]
    for index, job in enumerate(visible, start=start):
        marker = ">" if index == selected else " "
        job_text = f"{job.job_id}  {_short(job.command, max(20, width - 28))}"
        lines.append(f"{marker} {job.status[:8].ljust(8)} {job.kind[:5].ljust(5)} {job_text}")
    lines.append(divider)
    return "\n".join(lines)

