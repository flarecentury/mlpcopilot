import json

import pytest

from mlpcopilot.runtime.approval import ApprovalManager, resume_approved_action, tool_approval_error
from mlpcopilot.runtime.artifacts import ArtifactIndex
from mlpcopilot.runtime.profiles import MLPCOPILOT_TOOL_APPROVAL_ALLOWLIST


class _ReadOnlyTool:
    read_only = True


class _ExecTool:
    parameters = {"type": "object", "properties": {"approval_id": {"type": "string"}}}

    def __init__(self, result: str = "ok"):
        self.calls = []
        self.result = result

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class _ApprovalOwningExecTool(_ExecTool):
    approval_required = True


class _Tools:
    def __init__(self, tool, name="exec"):
        self.tool = tool
        self.name = name

    def get(self, name):
        return self.tool if name == self.name else None


class _Loop:
    def __init__(self, tool, name="exec", workspace=None):
        self.tools = _Tools(tool, name=name)
        self.workspace = workspace


class _McpTool:
    def __init__(self, result: str):
        self.result = result
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class _ManifestCreatingMcpTool(_McpTool):
    def __init__(self, workspace, result: str):
        super().__init__(result)
        self.workspace = workspace

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        ArtifactIndex(self.workspace).create_run(
            run_id=kwargs["run_id"],
            source="mcp:trainingController:start_training_run",
        )
        return self.result


def test_approval_manager_creates_and_decides_records(tmp_path) -> None:
    manager = ApprovalManager(tmp_path)
    ArtifactIndex(tmp_path).create_run(run_id="run_1", source="mcp:test:tool")

    record = manager.create(
        action_type="costly_job",
        title="Run validation",
        request="Launch expensive validation job",
        requester="agent",
        run_id="run_1",
    )

    assert record.status == "pending"
    assert manager.get(record.approval_id).title == "Run validation"
    assert len(manager.list_pending()) == 1

    decided = manager.approve(record.approval_id, decided_by="user", reason="ok")

    assert decided.status == "approved"
    assert decided.decided_by == "user"
    assert decided.reason == "ok"
    assert manager.list_pending() == []
    assert manager.list_decisions()[0].approval_id == record.approval_id
    manifest = ArtifactIndex(tmp_path).load("run_1")
    assert manifest.approval["approval_id"] == record.approval_id
    assert manifest.decisions[0]["approval_id"] == record.approval_id


def test_approval_manager_rejects_unknown_id(tmp_path) -> None:
    with pytest.raises(KeyError):
        ApprovalManager(tmp_path).reject("missing")


def test_tool_approval_policy_allows_readonly_tools_and_gates_writes(tmp_path) -> None:
    assert tool_approval_error(
        tmp_path,
        tool_name="web_fetch",
        arguments={"url": "https://example.com"},
        tool=_ReadOnlyTool(),
    ) is None
    assert "Approval required" in tool_approval_error(
        tmp_path,
        tool_name="write_file",
        arguments={"path": "a.txt", "content": "x"},
        tool=None,
    )
    assert "Approval required" in tool_approval_error(
        tmp_path,
        tool_name="edit_file",
        arguments={"path": "b.txt", "old_text": "", "new_text": "x"},
        tool=None,
    )
    assert len(ApprovalManager(tmp_path).list_pending()) == 2


def test_tool_approval_policy_allows_default_read_tools_by_exact_allowlist(tmp_path) -> None:
    read_only_calls = [
        ("read_file", {"path": "PROJECT.md"}),
        ("file_info", {"path": "PROJECT.md"}),
        ("list_dir", {"path": "."}),
        ("grep", {"pattern": "x", "path": "."}),
        ("glob", {"pattern": "**/*.md"}),
        ("web_search", {"query": "DeepMD-kit v3"}),
        ("web_fetch", {"url": "https://example.com"}),
    ]
    for tool_name, arguments in read_only_calls:
        assert tool_approval_error(
            tmp_path,
            tool_name=tool_name,
            arguments=arguments,
            approval_allowlist=MLPCOPILOT_TOOL_APPROVAL_ALLOWLIST,
        ) is None
    assert ApprovalManager(tmp_path).list_pending() == []


def test_tool_approval_policy_gates_existing_file_tools(tmp_path) -> None:
    target = tmp_path / "a.txt"
    target.write_text("old", encoding="utf-8")

    blocked = tool_approval_error(
        tmp_path,
        tool_name="edit_file",
        arguments={"path": "a.txt", "old_text": "old", "new_text": "new"},
        tool=None,
    )
    pending = ApprovalManager(tmp_path).list_pending()

    assert "Approval required" in blocked
    assert len(pending) == 1
    assert pending[0].metadata["tool"] == "edit_file"
    assert pending[0].metadata["path"] == "a.txt"


def test_tool_approval_policy_gates_mcp_tools(tmp_path) -> None:
    blocked = tool_approval_error(
        tmp_path,
        tool_name="mcp_dataset_validate",
        arguments={"dataset": "data.extxyz"},
        tool=None,
    )
    pending = ApprovalManager(tmp_path).list_pending()

    assert "Approval required" in blocked
    assert len(pending) == 1
    assert pending[0].metadata["tool"] == "mcp_dataset_validate"


def test_tool_approval_policy_allows_readonly_mcp_tools_without_allowlist(tmp_path) -> None:
    blocked = tool_approval_error(
        tmp_path,
        tool_name="mcp_dataset_inspect_dataset",
        arguments={"dataset_path": "data.extxyz"},
        tool=_ReadOnlyTool(),
    )

    assert blocked is None
    assert ApprovalManager(tmp_path).list_pending() == []


def test_tool_approval_policy_allows_exact_tool_allowlist(tmp_path) -> None:
    blocked = tool_approval_error(
        tmp_path,
        tool_name="mcp_agentic-file-search_agentic_explore",
        arguments={"task": "check database status"},
        approval_allowlist=["mcp_agentic-file-search_agentic_explore"],
    )

    assert blocked is None
    assert ApprovalManager(tmp_path).list_pending() == []


def test_tool_approval_policy_gates_my_check_without_allowlist(tmp_path) -> None:
    blocked = tool_approval_error(
        tmp_path,
        tool_name="my",
        arguments={"action": "check", "key": "exec_config"},
    )

    assert "Approval required" in blocked
    assert ApprovalManager(tmp_path).list_pending()[0].metadata["tool"] == "my"


def test_tool_approval_policy_still_gates_my_set(tmp_path) -> None:
    blocked = tool_approval_error(
        tmp_path,
        tool_name="my",
        arguments={"action": "set", "key": "model", "value": "x"},
    )

    assert "Approval required" in blocked
    assert ApprovalManager(tmp_path).list_pending()[0].metadata["tool"] == "my"


def test_tool_approval_policy_allowlist_is_exact(tmp_path) -> None:
    blocked = tool_approval_error(
        tmp_path,
        tool_name="mcp_agentic-file-search_other_tool",
        arguments={"task": "check database status"},
        approval_allowlist=["mcp_agentic-file-search_agentic_explore"],
    )

    assert "Approval required" in blocked
    assert ApprovalManager(tmp_path).list_pending()[0].metadata["tool"] == (
        "mcp_agentic-file-search_other_tool"
    )


def test_tool_approval_decision_does_not_authorize_future_calls(tmp_path) -> None:
    blocked = tool_approval_error(
        tmp_path,
        tool_name="my",
        arguments={"action": "set", "key": "model", "value": "x"},
        tool=None,
    )
    first = ApprovalManager(tmp_path).list_pending()[0]
    ApprovalManager(tmp_path).approve(first.approval_id, decided_by="test")

    blocked_again = tool_approval_error(
        tmp_path,
        tool_name="my",
        arguments={"action": "set", "key": "model", "value": "x"},
        tool=None,
    )
    pending = ApprovalManager(tmp_path).list_pending()

    assert "Approval required" in blocked
    assert "Approval required" in blocked_again
    assert len(pending) == 1
    assert pending[0].approval_id != first.approval_id


def test_tool_approval_policy_gates_exec_and_reuses_pending(tmp_path) -> None:
    first = tool_approval_error(
        tmp_path,
        tool_name="exec",
        arguments={"command": "ls"},
        tool=None,
    )
    second = tool_approval_error(
        tmp_path,
        tool_name="exec",
        arguments={"command": "ls"},
        tool=None,
    )
    pending = ApprovalManager(tmp_path).list_pending()

    assert "Approval required" in first
    assert "Approval required" in second
    assert len(pending) == 1
    assert pending[0].action_type == "tool_execution"
    assert pending[0].metadata["tool"] == "exec"


def test_tool_approval_policy_defers_to_exec_tool_own_approval_flow(tmp_path) -> None:
    assert tool_approval_error(
        tmp_path,
        tool_name="exec",
        arguments={"command": "ls -al"},
        tool=_ApprovalOwningExecTool(),
    ) is None
    assert ApprovalManager(tmp_path).list_pending() == []


@pytest.mark.asyncio
async def test_resume_approved_tool_execution_replays_arguments(tmp_path) -> None:
    record = ApprovalManager(tmp_path).create(
        action_type="tool_execution",
        title="Approve exec",
        request="exec",
        metadata={
            "tool": "exec",
            "arguments": {"command": "ls"},
            "args_hash": "unused",
        },
    )
    approved = ApprovalManager(tmp_path).approve(record.approval_id, decided_by="test")
    tool = _ExecTool()

    result = await resume_approved_action(_Loop(tool), approved)

    assert result == "Resumed exec after approval:\nok"
    assert tool.calls == [{"command": "ls", "approval_id": record.approval_id}]


@pytest.mark.asyncio
async def test_resume_approved_exec_preserves_terminal_output_spacing(tmp_path) -> None:
    record = ApprovalManager(tmp_path).create(
        action_type="tool_execution",
        title="Approve exec",
        request="exec",
        metadata={
            "tool": "exec",
            "arguments": {"command": "neofetch"},
            "args_hash": "unused",
        },
    )
    approved = ApprovalManager(tmp_path).approve(record.approval_id, decided_by="test")
    output = "      .-/+oossssoo+/-.               flare@host\n   `:+ssssssssssssssssss+:`           OS: Ubuntu"
    tool = _ExecTool(output)

    result = await resume_approved_action(_Loop(tool), approved)

    assert result == f"Resumed exec after approval:\n{output}"


@pytest.mark.asyncio
async def test_resume_approved_exec_preserves_background_argument(tmp_path) -> None:
    record = ApprovalManager(tmp_path).create(
        action_type="exec_command",
        title="Run background job",
        request="exec",
        metadata={
            "tool": "exec",
            "command": "long-train",
            "working_dir": str(tmp_path),
            "background": True,
        },
    )
    approved = ApprovalManager(tmp_path).approve(record.approval_id, decided_by="test")
    tool = _ExecTool("Background exec started.\nPID: 123")

    result = await resume_approved_action(_Loop(tool), approved)

    assert result == "Resumed exec after approval:\nBackground exec started.\nPID: 123"
    assert tool.calls == [
        {
            "command": "long-train",
            "working_dir": str(tmp_path),
            "background": True,
            "approval_id": record.approval_id,
        }
    ]


@pytest.mark.asyncio
async def test_resume_approved_mcp_tool_displays_answer_not_raw_payload(tmp_path) -> None:
    tool_name = "mcp_agentic-file-search_agentic_explore"
    record = ApprovalManager(tmp_path).create(
        action_type="tool_execution",
        title="Approve MCP tool",
        request="mcp",
        metadata={
            "tool": tool_name,
            "arguments": {"task": "check database status"},
            "args_hash": "unused",
        },
    )
    approved = ApprovalManager(tmp_path).approve(record.approval_id, decided_by="test")
    raw_result = json.dumps(
        {
            "agent": {"model": "qwen3.5-35b", "steps": 1, "use_index": True},
            "answer": "Database Status Check Results\n\nThe index is fresh.",
            "trace": [{"tool": "list_indexed_documents"}],
        },
        ensure_ascii=False,
    )
    tool = _McpTool(raw_result)

    result = await resume_approved_action(_Loop(tool, name=tool_name), approved)

    assert result == (
        "Resumed MCP tool after approval:\n"
        "Database Status Check Results\n\nThe index is fresh."
    )
    assert '"trace"' not in result
    assert '"agent"' not in result
    assert tool.calls == [{"task": "check database status"}]


@pytest.mark.asyncio
async def test_resume_approved_training_controller_mcp_replays_without_plugin_approval_flag(tmp_path) -> None:
    tool_name = "mcp_trainingController_start_training_run"
    args = {
        "project_path": str(tmp_path / "dpgen"),
        "param_path": str(tmp_path / "dpgen" / "param.json"),
        "machine_path": str(tmp_path / "dpgen" / "machine.json"),
        "run_id": "run_local",
    }
    blocked = tool_approval_error(
        tmp_path,
        tool_name=tool_name,
        arguments=args,
        tool=None,
    )
    pending = ApprovalManager(tmp_path).list_pending()

    assert "Approval required" in blocked
    assert len(pending) == 1
    assert pending[0].run_id == "run_local"
    assert pending[0].metadata["tool"] == tool_name
    assert pending[0].metadata["arguments"] == args

    approved = ApprovalManager(tmp_path).approve(pending[0].approval_id, decided_by="test")
    tool = _McpTool(json.dumps({"status": "success", "summary": "started"}, ensure_ascii=False))

    result = await resume_approved_action(_Loop(tool, name=tool_name), approved)

    assert result.startswith("Resumed MCP tool after approval:")
    assert tool.calls == [args]
    assert "approval_id" not in tool.calls[0]
    assert "approved" not in tool.calls[0]


@pytest.mark.asyncio
async def test_resume_approved_mcp_syncs_decision_after_manifest_creation(tmp_path) -> None:
    tool_name = "mcp_trainingController_start_training_run"
    args = {"project_path": str(tmp_path), "run_id": "run_after_approval"}
    blocked = tool_approval_error(
        tmp_path,
        tool_name=tool_name,
        arguments=args,
        tool=None,
    )
    pending = ApprovalManager(tmp_path).list_pending()

    assert "Approval required" in blocked
    approved = ApprovalManager(tmp_path).approve(pending[0].approval_id, decided_by="test")
    tool = _ManifestCreatingMcpTool(
        tmp_path,
        json.dumps({"status": "success", "summary": "started"}, ensure_ascii=False),
    )

    result = await resume_approved_action(_Loop(tool, name=tool_name, workspace=tmp_path), approved)

    manifest = ArtifactIndex(tmp_path).load("run_after_approval")
    assert result.startswith("Resumed MCP tool after approval:")
    assert manifest.decisions[0]["approval_id"] == approved.approval_id
    assert manifest.approval["approval_id"] == approved.approval_id


def test_artifact_index_creates_lists_and_loads_manifests(tmp_path) -> None:
    index = ArtifactIndex(tmp_path)

    manifest = index.create_run(
        source="mcp:dataset:inspect",
        inputs=[{"dataset": "datasets/a.extxyz"}],
        outputs=[{"report": "reports/a.md"}],
        artifacts=[
            {
                "artifact_id": "art_report",
                "type": "report",
                "path": "reports/a.md",
                "sha256": "abcdef1234567890",
                "produced_by": "mcp:dataset:inspect",
            }
        ],
        metrics=[
            {
                "name": "force_rmse",
                "value": 0.08,
                "unit": "eV/A",
                "source_artifact": "art_report",
            }
        ],
        lineage={
            "inputs": [{"path": "datasets/a.extxyz", "type": "dataset"}],
            "parents": ["run_previous"],
        },
        decisions=[{"approval_id": "apr_1", "status": "approved"}],
        approval={"approval_id": "apr_1", "status": "approved"},
    )

    manifest_path = tmp_path / "runs" / manifest.run_id / "manifest.json"
    assert manifest_path.exists()
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert raw["source"] == "mcp:dataset:inspect"
    assert raw["artifacts"][0]["artifact_id"] == "art_report"
    assert raw["metrics"][0]["name"] == "force_rmse"
    assert raw["lineage"]["parents"] == ["run_previous"]
    assert raw["decisions"][0]["approval_id"] == "apr_1"

    listed = index.list_runs()
    assert [item.run_id for item in listed] == [manifest.run_id]

    loaded = index.load(manifest.run_id)
    assert loaded.artifacts[0]["path"] == "reports/a.md"
    assert loaded.metrics[0]["source_artifact"] == "art_report"
    assert loaded.lineage["inputs"][0]["path"] == "datasets/a.extxyz"
    assert loaded.decisions[0]["status"] == "approved"

    updated = index.update(manifest.run_id, metrics=[{"name": "energy_mae", "value": 1.2}])

    assert updated.metrics == [{"name": "energy_mae", "value": 1.2}]


def test_artifact_index_loads_legacy_manifests_without_evidence_fields(tmp_path) -> None:
    run_dir = tmp_path / "runs" / "run_legacy"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "run_legacy",
                "created_at": "2026-01-01T00:00:00+00:00",
                "source": "mcp:legacy",
                "artifacts": ["reports/legacy.md"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    manifest = ArtifactIndex(tmp_path).load("run_legacy")

    assert manifest.artifacts == ["reports/legacy.md"]
    assert manifest.metrics == []
    assert manifest.lineage == {}
    assert manifest.decisions == []
