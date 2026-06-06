# Release Readiness Checklist

Use this checklist before tagging, publishing, or handing a build to users for
real MLP/DP-GEN work.

## Source Of Truth

- PRD files under `prd/` reflect the intended behavior.
- Runtime/plugin boundary is still respected.
- `README.md`, `PROJECT.md`, and `AGENTS.md` agree with the PRDs.
- `docs/README.md` links every current implementation-facing doc.
- `docs/MAINTENANCE.md` placement rules are still accurate.

## Runtime Defaults

- `runtimeProfile = "mlpcopilot"` applies defaults only when fields are absent.
- Explicit user policy config is preserved exactly.
- Default root remains `~/.mlpcopilot`.
- Default workspace remains `~/.mlpcopilot/workspace`.
- Workspace initialization creates the same files described in docs:
  `AGENTS.md`, `TOOLS.md`, `PROJECT.md`, `memory/`, `projects/`, `runs/`,
  `artifacts/`, `approvals/`, `reports/`, and related schema directories.
- `agentic-file-search` is available by default when its MCP server is
  configured or source-discovered.

## Approval And Tool Policy

- Built-in tools and MCP tools go through one runtime approval policy.
- Exact `tools.approvalAllowlist` entries bypass approval when intended.
- MCP tools do not implement approval bypass shims.
- State-changing tools produce pending approvals in TUI/API/Telegram flows.
- Approval decisions persist across restart.
- TUI `!<cmd>` remains explicit terminal mode and is documented separately from
  agent tool approval.

## MCP And Skill Inventory

- `mlpcopilot mlp capabilities` lists expected MCP servers and skills.
- `trainingController` exposes the expected enabled tool subset.
- Dataset, model-eval, report, and agentic-file-search MCP servers start from
  the source tree.
- MLP skills are discoverable:
  `mlp-active-learning`, `dpgen-machine-writer`,
  `mlp-initial-dataset-preparation`, `mlp-dataset-validation`,
  `mlp-checkpoint-evaluation`, `mlp-validation-planner`,
  `mlp-ood-test-advisor`.
- Disabled generic skills remain disabled by default unless intentionally
  changed.

## DP-GEN Operation Smoke

When a sample DP-GEN workdir is available:

```bash
bash run_tui.sh --dpgen-dir /path/to/dpgen --once
```

Confirm:

- workspace initializes cleanly;
- project and run are created or reused;
- `backend/dpgen` points to the intended workdir or copy;
- `mlp runs sync-dpgen` succeeds;
- TUI Campaign and Artifacts panels show run state;
- logs and artifact records use paths/hashes rather than pasted payloads.

For rewind behavior, use a disposable copy or fixture:

- `plan_training_rewind` runs before any apply/reset tool;
- `soft` mode preserves iteration directories;
- archive mode archives later iteration directories and does not delete them;
- snapshot and approval evidence are recorded.

## Scientific Evidence

- Dataset claims cite dataset MCP artifacts or user-provided reports.
- Checkpoint claims cite model-eval MCP artifacts, `dp test` output, or
  normalized metrics artifacts.
- Validation plans are project-specific and include missing evidence rather than
  filling gaps with LLM guesses.
- Reports are evidence aggregation, not metric invention.
- Large structures, trajectories, force arrays, and datasets stay as paths or
  artifact references.

## Documentation

- New or moved docs are listed in `docs/README.md`.
- Subdirectory indexes are updated.
- Local Markdown links pass a lightweight check.
- Command examples match current CLI signatures.
- Runbooks state assumptions and approval requirements.
- Upstream docs remain clearly labeled as inherited reference material.

Suggested local link check:

```bash
python3 - <<'PY'
from pathlib import Path
import re

roots = [Path("README.md"), Path("PROJECT.md"), Path("AGENTS.md")]
roots += list(Path("docs").rglob("*.md"))
roots += list(Path("prd").rglob("*.md"))
pattern = re.compile(r"\\[[^\\]]+\\]\\(([^)]+)\\)")
missing = []

for path in roots:
    if not path.exists():
        continue
    for raw in pattern.findall(path.read_text(encoding="utf-8")):
        link = raw.strip()
        if not link or link.startswith(("#", "http://", "https://", "mailto:")):
            continue
        if "://" in link:
            continue
        target = link.split("#", 1)[0].split("?", 1)[0]
        if target and not (path.parent / target).resolve().exists():
            missing.append((str(path), link))

if missing:
    for source, link in missing:
        print(f"{source}: missing {link}")
    raise SystemExit(1)
print("local markdown links ok")
PY
```

## Test And Hygiene

Run focused checks for changed areas, then full checks before release:

```bash
uv run --extra dev ruff check mlpcopilot tests
uv run --extra dev pytest -q
```

Confirm the repository does not contain generated artifacts:

- no nested MCP `.venv` directories;
- no `.pytest_cache`, `.ruff_cache`, `.ipynb_checkpoints`;
- no committed `__pycache__` or `.pyc`;
- no root runtime workspace residue such as `jobs/`, `memory/`, `runs/`, or
  `artifacts/`.

Check Git state:

```bash
git status --short
git diff --stat
```

Do not delete user data or Git history as part of release hygiene.
