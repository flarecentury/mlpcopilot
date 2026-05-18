"""
Helpers for recording exploration path and referenced files.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any


FILE_TOOLS: frozenset[str] = frozenset({"read", "grep", "preview_file", "parse_file"})

# Matches citations like: [Source: filename.pdf, Section 2.1]
SOURCE_CITATION_RE = re.compile(r"\[Source:\s*([^,\]]+)")


def normalize_path(path: str, root_directory: str) -> str:
    """Return an absolute path using root_directory for relative inputs."""
    if os.path.isabs(path):
        return os.path.abspath(path)
    return os.path.abspath(os.path.join(root_directory, path))


def extract_cited_sources(final_result: str | None) -> list[str]:
    """Extract source labels from final answer citations while preserving order."""
    if not final_result:
        return []

    seen: set[str] = set()
    ordered_sources: list[str] = []

    for raw_source in SOURCE_CITATION_RE.findall(final_result):
        source = raw_source.strip()
        if source and source not in seen:
            seen.add(source)
            ordered_sources.append(source)

    return ordered_sources


@dataclass
class ExplorationTrace:
    """
    Collects a step-by-step path and files referenced by tool calls.

    Paths are normalized to absolute paths to make replay/debugging easier.
    """

    root_directory: str
    step_path: list[str] = field(default_factory=list)
    referenced_documents: set[str] = field(default_factory=set)

    def record_tool_call(
        self,
        *,
        step_number: int,
        tool_name: str,
        tool_input: dict[str, Any],
        resolved_document_path: str | None = None,
    ) -> None:
        """Record a tool call in the exploration path."""
        path_entries: list[str] = []

        directory = tool_input.get("directory")
        if isinstance(directory, str) and directory:
            path_entries.append(f"directory={normalize_path(directory, self.root_directory)}")

        file_path = tool_input.get("file_path")
        if isinstance(file_path, str) and file_path:
            normalized_file_path = normalize_path(file_path, self.root_directory)
            path_entries.append(f"file={normalized_file_path}")
            if tool_name in FILE_TOOLS:
                self.referenced_documents.add(normalized_file_path)

        if resolved_document_path:
            normalized_doc_path = normalize_path(resolved_document_path, self.root_directory)
            path_entries.append(f"document={normalized_doc_path}")
            self.referenced_documents.add(normalized_doc_path)

        parameters = ", ".join(path_entries) if path_entries else "no-path-args"
        self.step_path.append(f"{step_number}. tool:{tool_name} ({parameters})")

    def record_go_deeper(self, *, step_number: int, directory: str) -> None:
        """Record a directory navigation event in the exploration path."""
        resolved_dir = normalize_path(directory, self.root_directory)
        self.step_path.append(f"{step_number}. godeeper (directory={resolved_dir})")

    def sorted_documents(self) -> list[str]:
        """Return a sorted list of referenced documents."""
        return sorted(self.referenced_documents)
