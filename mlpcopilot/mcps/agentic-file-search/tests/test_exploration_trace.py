"""Tests for exploration trace helpers."""

import os

from fs_explorer.exploration_trace import (
    ExplorationTrace,
    extract_cited_sources,
    normalize_path,
)


def test_normalize_path_relative() -> None:
    root = "/tmp/project"
    assert normalize_path("docs/file.pdf", root) == os.path.abspath("/tmp/project/docs/file.pdf")


def test_normalize_path_absolute() -> None:
    root = "/tmp/project"
    assert normalize_path("/var/data/file.pdf", root) == os.path.abspath("/var/data/file.pdf")


def test_trace_records_steps_and_documents() -> None:
    trace = ExplorationTrace(root_directory="/tmp/project")

    trace.record_tool_call(
        step_number=1,
        tool_name="scan_folder",
        tool_input={"directory": "docs"},
    )
    trace.record_tool_call(
        step_number=2,
        tool_name="parse_file",
        tool_input={"file_path": "docs/contract.pdf"},
    )
    trace.record_go_deeper(step_number=3, directory="docs/subdir")

    assert len(trace.step_path) == 3
    assert "tool:scan_folder" in trace.step_path[0]
    assert "tool:parse_file" in trace.step_path[1]
    assert "godeeper" in trace.step_path[2]

    referenced = trace.sorted_documents()
    assert len(referenced) == 1
    assert referenced[0].endswith("docs/contract.pdf")


def test_trace_records_resolved_document_paths() -> None:
    trace = ExplorationTrace(root_directory="/tmp/project")

    trace.record_tool_call(
        step_number=1,
        tool_name="get_document",
        tool_input={"doc_id": "doc_123"},
        resolved_document_path="/tmp/project/docs/indexed.pdf",
    )

    assert "document=/tmp/project/docs/indexed.pdf" in trace.step_path[0]
    assert trace.sorted_documents() == ["/tmp/project/docs/indexed.pdf"]


def test_extract_cited_sources_ordered_unique() -> None:
    final_result = (
        "Price is $10M [Source: agreement.pdf, Section 2.1]. "
        "Escrow is $1M [Source: escrow.pdf, Section 3]. "
        "Reconfirmed [Source: agreement.pdf, Section 2.1]."
    )
    assert extract_cited_sources(final_result) == ["agreement.pdf", "escrow.pdf"]
