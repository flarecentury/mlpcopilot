"""Indexable file extension configuration."""

from __future__ import annotations

import os
import re

from ..fs import SUPPORTED_EXTENSIONS

EXTRA_INDEXABLE_EXTENSIONS_ENV = "FS_EXPLORER_EXTRA_INDEXABLE_EXTENSIONS"

_INDEXABLE_TEXT_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".txt",
        ".text",
        ".sh",
        ".bash",
        ".zsh",
        ".py",
        ".js",
        ".ts",
        ".json",
        ".jsonl",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".log",
        ".csv",
        ".tsv",
        ".xml",
        ".inp",
        ".in",
        ".input",
        ".lmp",
        ".lammps",
    }
)
INDEXABLE_EXTENSIONS: frozenset[str] = SUPPORTED_EXTENSIONS | _INDEXABLE_TEXT_EXTENSIONS


def _parse_extension_list(raw: str | None) -> frozenset[str]:
    if raw is None or raw.strip() == "":
        return frozenset()
    extensions: set[str] = set()
    for token in re.split(r"[,;\s]+", raw):
        ext = token.strip().lower()
        if not ext:
            continue
        if ext.startswith("*."):
            ext = ext[1:]
        elif ext.startswith("*"):
            ext = ext.lstrip("*")
        if ext and not ext.startswith("."):
            ext = f".{ext}"
        if ext != ".":
            extensions.add(ext)
    return frozenset(extensions)


def get_extra_indexable_extensions() -> frozenset[str]:
    """Return user-configured text extensions to index in addition to defaults."""
    return _parse_extension_list(os.getenv(EXTRA_INDEXABLE_EXTENSIONS_ENV))


def get_indexable_text_extensions() -> frozenset[str]:
    """Return plain-text extensions that can be read directly for indexing."""
    return _INDEXABLE_TEXT_EXTENSIONS | get_extra_indexable_extensions()


def get_indexable_extensions() -> frozenset[str]:
    """Return all extensions considered by indexing and freshness checks."""
    return SUPPORTED_EXTENSIONS | get_indexable_text_extensions()
