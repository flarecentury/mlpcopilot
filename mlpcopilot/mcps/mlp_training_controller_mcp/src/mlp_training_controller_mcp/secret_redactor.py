"""Secret redaction utilities for training controller configs and logs."""

from __future__ import annotations

import re
from typing import Any

SECRET_KEY_PARTS = (
    "password",
    "passwd",
    "token",
    "secret",
    "private_key",
    "passphrase",
    "api_key",
    "access_key",
)

SECRET_LINE_PATTERNS = (
    re.compile(r"(?i)(password\s*[:=]\s*)([^,\s}\]]+)"),
    re.compile(r"(?i)(token\s*[:=]\s*)([^,\s}\]]+)"),
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)([^,\s}\]]+)"),
    re.compile(r"(?i)(secret\s*[:=]\s*)([^,\s}\]]+)"),
)


def is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SECRET_KEY_PARTS)


def redact_value(value: Any) -> str:
    if value in (None, ""):
        return ""
    return "<redacted>"


def redact_mapping(value: Any, *, path: str = "$") -> tuple[Any, list[str]]:
    """Return a redacted copy and paths where secrets were found."""
    findings: list[str] = []

    def _walk(node: Any, current: str) -> Any:
        if isinstance(node, dict):
            redacted: dict[str, Any] = {}
            for key, item in node.items():
                child_path = f"{current}.{key}"
                if is_secret_key(str(key)):
                    findings.append(child_path)
                    redacted[key] = redact_value(item)
                else:
                    redacted[key] = _walk(item, child_path)
            return redacted
        if isinstance(node, list):
            return [_walk(item, f"{current}[{idx}]") for idx, item in enumerate(node)]
        return node

    return _walk(value, path), findings


def redact_text(text: str) -> str:
    """Redact common inline secret assignments in log/config snippets."""
    redacted = text
    for pattern in SECRET_LINE_PATTERNS:
        redacted = pattern.sub(r"\1<redacted>", redacted)
    return redacted

