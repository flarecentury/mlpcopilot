"""
Metadata filter parsing helpers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal


FilterOperator = Literal["eq", "ne", "gt", "gte", "lt", "lte", "in", "contains"]


@dataclass(frozen=True)
class MetadataFilter:
    """Normalized metadata filter condition."""

    field: str
    operator: FilterOperator
    value: str | bool | int | float | list[str | bool | int | float]

    def to_storage_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "operator": self.operator,
            "value": self.value,
        }


class MetadataFilterParseError(ValueError):
    """Raised when metadata filter syntax is invalid."""


_FIELD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")


def supported_filter_syntax() -> str:
    """Return a short help text for filter syntax."""
    return (
        "Supported filter syntax: "
        "`field=value`, `field!=value`, `field>=number`, `field<=number`, "
        "`field>number`, `field<number`, `field in (a, b, c)`, `field~substring`; "
        "combine with comma or `and`."
    )


def parse_metadata_filters(
    raw_filters: str | None,
    *,
    allowed_fields: set[str] | None = None,
) -> list[MetadataFilter]:
    """Parse a raw filter string into normalized metadata conditions."""
    if raw_filters is None or not raw_filters.strip():
        return []

    conditions = _split_conditions(raw_filters)
    parsed: list[MetadataFilter] = []
    for condition in conditions:
        parsed.append(_parse_condition(condition, allowed_fields=allowed_fields))
    return parsed


def _parse_condition(condition: str, *, allowed_fields: set[str] | None) -> MetadataFilter:
    text = condition.strip()
    if not text:
        raise MetadataFilterParseError("Empty filter condition.")

    in_match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s+in\s+(.+)\s*$", text, flags=re.IGNORECASE)
    if in_match:
        field = in_match.group(1)
        _validate_field(field, allowed_fields=allowed_fields)
        values = _parse_list_value(in_match.group(2))
        if not values:
            raise MetadataFilterParseError(f"`in` filter has no values: {text!r}")
        return MetadataFilter(field=field, operator="in", value=values)

    op_match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(<=|>=|!=|=|<|>|~|:)\s*(.+)\s*$", text)
    if not op_match:
        raise MetadataFilterParseError(f"Invalid filter syntax: {text!r}")

    field = op_match.group(1)
    operator_symbol = op_match.group(2)
    raw_value = op_match.group(3)
    _validate_field(field, allowed_fields=allowed_fields)
    value = _parse_scalar_value(raw_value)

    operator_map: dict[str, FilterOperator] = {
        "=": "eq",
        ":": "eq",
        "!=": "ne",
        ">": "gt",
        ">=": "gte",
        "<": "lt",
        "<=": "lte",
        "~": "contains",
    }
    operator = operator_map[operator_symbol]

    if operator in {"gt", "gte", "lt", "lte"} and not isinstance(value, (int, float)):
        raise MetadataFilterParseError(
            f"Operator `{operator_symbol}` requires a numeric value: {text!r}"
        )

    return MetadataFilter(field=field, operator=operator, value=value)


def _validate_field(field: str, *, allowed_fields: set[str] | None) -> None:
    if not _FIELD_RE.match(field):
        raise MetadataFilterParseError(f"Invalid field name: {field!r}")
    if allowed_fields is not None and field not in allowed_fields:
        allowed = ", ".join(sorted(allowed_fields)) if allowed_fields else "<none>"
        raise MetadataFilterParseError(
            f"Unknown metadata field {field!r}. Allowed fields: {allowed}"
        )


def _split_conditions(raw: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    quote: str | None = None
    paren_depth = 0
    bracket_depth = 0
    i = 0
    while i < len(raw):
        ch = raw[i]

        if quote is not None:
            current.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue

        if ch in {"'", '"'}:
            quote = ch
            current.append(ch)
            i += 1
            continue
        if ch == "(":
            paren_depth += 1
            current.append(ch)
            i += 1
            continue
        if ch == ")":
            paren_depth = max(paren_depth - 1, 0)
            current.append(ch)
            i += 1
            continue
        if ch == "[":
            bracket_depth += 1
            current.append(ch)
            i += 1
            continue
        if ch == "]":
            bracket_depth = max(bracket_depth - 1, 0)
            current.append(ch)
            i += 1
            continue

        if paren_depth == 0 and bracket_depth == 0 and ch == ",":
            _flush_part(parts, current)
            i += 1
            continue

        if (
            paren_depth == 0
            and bracket_depth == 0
            and raw[i : i + 3].lower() == "and"
            and (i == 0 or raw[i - 1].isspace())
            and (i + 3 == len(raw) or raw[i + 3].isspace())
        ):
            _flush_part(parts, current)
            i += 3
            continue

        current.append(ch)
        i += 1

    _flush_part(parts, current)
    return parts


def _flush_part(parts: list[str], current: list[str]) -> None:
    text = "".join(current).strip()
    if text:
        parts.append(text)
    current.clear()


def _parse_list_value(raw_value: str) -> list[str | bool | int | float]:
    text = raw_value.strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    elif text.startswith("[") and text.endswith("]"):
        text = text[1:-1]

    if not text.strip():
        return []

    items = _split_conditions(text)
    return [_parse_scalar_value(item) for item in items]


def _parse_scalar_value(raw_value: str) -> str | bool | int | float:
    text = raw_value.strip()
    if not text:
        raise MetadataFilterParseError("Missing filter value.")

    if (text.startswith("'") and text.endswith("'")) or (
        text.startswith('"') and text.endswith('"')
    ):
        return text[1:-1]

    lower = text.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if _NUMBER_RE.match(text):
        if "." in text:
            return float(text)
        return int(text)
    return text
