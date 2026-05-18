from __future__ import annotations

import json
import sys
from pathlib import Path

MCP_SRC = Path(__file__).resolve().parents[1] / "mlpcopilot" / "mcps" / "mlp_report_mcp" / "src"
sys.path.insert(0, str(MCP_SRC))

from mlp_report_mcp.report import ReportBackend  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_mlp_report_mcp_builds_evidence_report(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    artifact_path = workspace / "reports" / "checkpoint_benchmark.md"
    output_path = workspace / "reports" / "evidence.md"
    _write(artifact_path, "# Checkpoint Benchmark Report\n")
    _write(
        workspace / "runs" / "run_model" / "manifest.json",
        json.dumps(
            {
                "run_id": "run_model",
                "created_at": "2026-05-09T00:00:00+00:00",
                "source": "mcp:mlp-model-eval:build_checkpoint_benchmark_report",
                "artifacts": [
                    {
                        "type": "report",
                        "path": str(artifact_path),
                        "sha256": "abc123",
                    }
                ],
                "metrics": [{"name": "force_rmse", "value": 0.08}],
                "decisions": [{"approval_id": "apr_done", "status": "approved"}],
            }
        ),
    )
    _write(
        workspace / "approvals" / "pending.jsonl",
        json.dumps(
            {
                "approval_id": "apr_pending",
                "status": "pending",
                "action_type": "run_tool",
                "title": "Run benchmark",
                "run_id": "run_model",
            }
        )
        + "\n",
    )
    _write(
        workspace / "approvals" / "decisions.jsonl",
        json.dumps(
            {
                "approval_id": "apr_done",
                "status": "approved",
                "action_type": "run_tool",
                "title": "Build report",
                "run_id": "run_model",
            }
        )
        + "\n",
    )

    payload = json.loads(
        ReportBackend().build_evidence_report(
            str(workspace),
            artifact_paths=[str(artifact_path)],
            output_path=str(output_path),
        )
    )

    assert payload["status"] == "success"
    assert payload["metrics"]["run_count"] == 1
    assert payload["metrics"]["artifact_count"] == 1
    assert payload["metrics"]["pending_approval_count"] == 1
    assert payload["metrics"]["decision_count"] == 1
    assert payload["artifacts"][0]["type"] == "report"
    content = output_path.read_text(encoding="utf-8")
    assert "MLP Evidence Report" in content
    assert "run_model" in content
    assert "apr_pending" in content
    assert "apr_done" in content
    assert "abc123" in content
    assert "does not create scientific metrics" in content
