"""
Metadata extraction helpers for indexed documents.
"""

from __future__ import annotations

import copy
import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


_CURRENCY_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?")
_DATE_RE = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2},\s+\d{4})\b",
    flags=re.IGNORECASE,
)
_DOC_TYPE_TOKEN_RE = re.compile(r"[a-z0-9]+")
_DOC_TYPE_STOPWORDS: set[str] = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "copy",
    "draft",
    "final",
    "version",
    "v1",
    "v2",
    "v3",
    "new",
    "old",
    "tmp",
    "temp",
}

_LANGEXTRACT_PROMPT_DESCRIPTION = (
    "Extract key transaction metadata from legal and deal documents. "
    "Use extraction classes: organization, person, money, date, deal_term. "
    "Use exact spans from the source text and avoid paraphrasing."
)

_VALID_METADATA_FIELD_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_VALID_FIELD_TYPES: set[str] = {"string", "integer", "number", "boolean"}
_VALID_RUNTIME_FIELDS: set[str] = {"enabled", "extraction_count", "entity_classes"}
_FIELD_MODE_ALIASES: dict[str, str] = {
    "csv": "values",
    "list": "values",
    "joined": "values",
    "join": "values",
    "values": "values",
    "count": "count",
    "exists": "exists",
    "contains": "contains",
    "contains_any": "contains",
}

_DEFAULT_LANGEXTRACT_PROFILE: dict[str, Any] = {
    "name": "default_langextract",
    "description": "Default metadata extraction profile for legal and deal-style documents.",
    "prompt_description": _LANGEXTRACT_PROMPT_DESCRIPTION,
    "fields": [
        {
            "name": "lx_enabled",
            "type": "boolean",
            "required": False,
            "description": "Whether langextract metadata extraction succeeded.",
            "source": "runtime",
            "runtime": "enabled",
        },
        {
            "name": "lx_extraction_count",
            "type": "integer",
            "required": False,
            "description": "Number of langextract entities extracted from the document.",
            "source": "runtime",
            "runtime": "extraction_count",
        },
        {
            "name": "lx_entity_classes",
            "type": "string",
            "required": False,
            "description": "Comma-separated extraction classes returned by langextract.",
            "source": "runtime",
            "runtime": "entity_classes",
        },
        {
            "name": "lx_organizations",
            "type": "string",
            "required": False,
            "description": "Comma-separated organization names extracted by langextract.",
            "source": "entities",
            "source_classes": ["organization", "company", "party"],
            "mode": "values",
        },
        {
            "name": "lx_people",
            "type": "string",
            "required": False,
            "description": "Comma-separated person names extracted by langextract.",
            "source": "entities",
            "source_classes": ["person", "individual", "executive"],
            "mode": "values",
        },
        {
            "name": "lx_deal_terms",
            "type": "string",
            "required": False,
            "description": "Comma-separated deal terms extracted by langextract.",
            "source": "entities",
            "source_classes": ["deal_term", "term", "provision"],
            "mode": "values",
        },
        {
            "name": "lx_money_mentions",
            "type": "integer",
            "required": False,
            "description": "Count of monetary amount entities from langextract.",
            "source": "entities",
            "source_classes": ["money", "amount", "currency"],
            "mode": "count",
        },
        {
            "name": "lx_date_mentions",
            "type": "integer",
            "required": False,
            "description": "Count of date entities from langextract.",
            "source": "entities",
            "source_classes": ["date"],
            "mode": "count",
        },
        {
            "name": "lx_has_earnout",
            "type": "boolean",
            "required": False,
            "description": "Whether extracted deal terms indicate an earnout.",
            "source": "entities",
            "source_classes": ["deal_term", "term", "provision"],
            "mode": "contains",
            "contains_any": ["earnout"],
        },
        {
            "name": "lx_has_escrow",
            "type": "boolean",
            "required": False,
            "description": "Whether extracted deal terms indicate escrow.",
            "source": "entities",
            "source_classes": ["deal_term", "term", "provision"],
            "mode": "contains",
            "contains_any": ["escrow"],
        },
    ],
}


_AUTO_PROFILE_PROMPT_TEMPLATE = (
    "You are a metadata schema designer. Analyze the document samples below and generate "
    "a langextract metadata extraction profile tailored to this corpus.\n\n"
    "Return a JSON object with these keys:\n"
    '- "name": a short descriptive profile name (string)\n'
    '- "description": one-sentence description of the profile (string)\n'
    '- "prompt_description": instruction text for the extraction model (string)\n'
    '- "fields": array of field definitions\n\n'
    "Each field object must have:\n"
    '- "name": valid identifier starting with "lx_" (letters, digits, underscores)\n'
    '- "type": one of "string", "integer", "number", "boolean"\n'
    '- "description": what this field captures\n'
    '- "source": "entities"\n'
    '- "source_classes": array of entity class names to aggregate (e.g. ["organization", "company"])\n'
    '- "mode": one of "values" (comma-joined text), "count" (integer count), "exists" (boolean), '
    '"contains" (boolean, requires "contains_any")\n'
    '- "contains_any": (only when mode is "contains") array of lowercase terms to match\n\n'
    "Valid entity source classes include (but are not limited to): organization, company, party, "
    "person, individual, executive, money, amount, currency, date, deal_term, term, provision, "
    "location, product, technology, regulation, clause, obligation.\n\n"
    "### Example profile for legal/M&A documents\n"
    "```json\n"
    '{"name": "legal_ma", "description": "Metadata extraction for legal and M&A deal documents.", '
    '"prompt_description": "Extract key transaction metadata from legal and deal documents.", '
    '"fields": ['
    '{"name": "lx_organizations", "type": "string", "description": "Organization names.", '
    '"source": "entities", "source_classes": ["organization", "company", "party"], "mode": "values"}, '
    '{"name": "lx_money_mentions", "type": "integer", "description": "Count of monetary amounts.", '
    '"source": "entities", "source_classes": ["money", "amount"], "mode": "count"}, '
    '{"name": "lx_has_escrow", "type": "boolean", "description": "Whether escrow terms are present.", '
    '"source": "entities", "source_classes": ["deal_term", "provision"], "mode": "contains", '
    '"contains_any": ["escrow"]}'
    "]}\n"
    "```\n\n"
    "### Example profile for technical/research documents\n"
    "```json\n"
    '{"name": "tech_research", "description": "Metadata extraction for technical and research documents.", '
    '"prompt_description": "Extract key entities from technical and research documents.", '
    '"fields": ['
    '{"name": "lx_technologies", "type": "string", "description": "Technology names.", '
    '"source": "entities", "source_classes": ["technology", "product"], "mode": "values"}, '
    '{"name": "lx_people", "type": "string", "description": "Person names.", '
    '"source": "entities", "source_classes": ["person", "individual"], "mode": "values"}, '
    '{"name": "lx_org_count", "type": "integer", "description": "Number of organizations mentioned.", '
    '"source": "entities", "source_classes": ["organization", "company"], "mode": "count"}'
    "]}\n"
    "```\n\n"
    "### Document samples from the corpus\n\n"
    "SAMPLES_PLACEHOLDER\n\n"
    "Generate a profile with 4-8 entity fields (do NOT include runtime fields). "
    "Return ONLY the JSON object, no markdown fencing."
)


def _get_genai_client(api_key: str) -> Any:
    """Instantiate a Google GenAI client. Separated for test patching."""
    from google.genai import Client as _GenAIClient

    return _GenAIClient(api_key=api_key)


def auto_discover_profile(
    folder: str,
    *,
    sample_count: int = 3,
    model_id: str | None = None,
) -> dict[str, Any]:
    """Use an LLM to generate a langextract profile tailored to the corpus.

    Falls back to the default hardcoded profile on any failure.
    """
    from .schema import _iter_supported_files

    files = _iter_supported_files(folder)
    if not files:
        return default_langextract_profile()

    # Sample files evenly
    n = min(sample_count, len(files))
    step = max(1, len(files) // n)
    sampled = [files[i * step] for i in range(n)]

    # Parse and truncate
    from ..fs import parse_file

    snippets: list[str] = []
    for file_path in sampled:
        try:
            text = parse_file(file_path)
            snippets.append(
                f"--- {Path(file_path).name} ---\n{text[:2000]}"
            )
        except Exception:
            continue

    if not snippets:
        return default_langextract_profile()

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return default_langextract_profile()

    effective_model = model_id or os.getenv(
        "FS_EXPLORER_PROFILE_MODEL", "gemini-2.0-flash"
    )

    try:
        client = _get_genai_client(api_key=api_key)
        prompt = _AUTO_PROFILE_PROMPT_TEMPLATE.replace(
            "SAMPLES_PLACEHOLDER", "\n\n".join(snippets)
        )
        response = client.models.generate_content(
            model=effective_model,
            contents=prompt,
        )
        raw_text = (response.text or "").strip()
        # Strip markdown fencing if present
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```[a-z]*\n?", "", raw_text)
            raw_text = re.sub(r"\n?```$", "", raw_text).strip()
        profile = json.loads(raw_text)
        # Add runtime fields that are always present
        runtime_fields = [
            f for f in _DEFAULT_LANGEXTRACT_PROFILE["fields"] if f.get("source") == "runtime"
        ]
        existing_names = {
            str(f.get("name")) for f in profile.get("fields", []) if isinstance(f, dict)
        }
        for rf in runtime_fields:
            if rf["name"] not in existing_names:
                profile.setdefault("fields", []).insert(0, copy.deepcopy(rf))
        return normalize_langextract_profile(profile)
    except Exception:
        return default_langextract_profile()


def infer_document_type(file_path: str) -> str:
    """Infer a generic document type from filename tokens."""
    stem = Path(file_path).stem.lower()
    tokens = [token for token in _DOC_TYPE_TOKEN_RE.findall(stem) if token]
    filtered = [
        token
        for token in tokens
        if not token.isdigit() and len(token) > 2 and token not in _DOC_TYPE_STOPWORDS
    ]
    if filtered:
        return filtered[-1]
    if tokens:
        return tokens[-1]
    return "document"


def default_langextract_profile() -> dict[str, Any]:
    """Return a mutable copy of the built-in metadata profile."""
    return copy.deepcopy(_DEFAULT_LANGEXTRACT_PROFILE)


def normalize_langextract_profile(profile: dict[str, Any] | None) -> dict[str, Any]:
    """
    Validate and normalize user-provided langextract profile configuration.

    Expected shape:
    - prompt_description: str (optional)
    - max_chars: int (optional)
    - fields: list[{
        name: str,
        type: string|integer|number|boolean,
        description: str (optional),
        required: bool (optional),
        source: runtime|entities (default entities),
        runtime: enabled|extraction_count|entity_classes (runtime source only),
        source_class: str (entities source),
        source_classes: list[str] (entities source),
        mode: values|count|exists|contains (entities source),
        contains_any: list[str] (contains mode),
      }]
    """
    raw = default_langextract_profile() if profile is None else copy.deepcopy(profile)
    if not isinstance(raw, dict):
        raise ValueError("Metadata profile must be a JSON object.")

    prompt = raw.get("prompt_description")
    if prompt is None:
        prompt_description = _LANGEXTRACT_PROMPT_DESCRIPTION
    elif isinstance(prompt, str) and prompt.strip():
        prompt_description = prompt.strip()
    else:
        raise ValueError(
            "Metadata profile field 'prompt_description' must be a non-empty string."
        )

    max_chars: int | None = None
    if "max_chars" in raw:
        max_chars = _safe_positive_int(
            raw.get("max_chars"),
            minimum=500,
            field_name="max_chars",
        )

    raw_fields = raw.get("fields")
    if not isinstance(raw_fields, list) or not raw_fields:
        raise ValueError("Metadata profile must include a non-empty 'fields' array.")

    normalized_fields: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for idx, raw_field in enumerate(raw_fields):
        if not isinstance(raw_field, dict):
            raise ValueError(f"Metadata field at index {idx} must be an object.")

        name_obj = raw_field.get("name")
        if not isinstance(name_obj, str) or not name_obj.strip():
            raise ValueError(
                f"Metadata field at index {idx} is missing a valid 'name'."
            )
        name = name_obj.strip()
        if not _VALID_METADATA_FIELD_NAME_RE.match(name):
            raise ValueError(
                f"Invalid metadata field name '{name}'. "
                "Use letters, numbers, and underscores."
            )
        if name in seen_names:
            raise ValueError(f"Duplicate metadata field name '{name}'.")
        seen_names.add(name)

        field_type = str(raw_field.get("type", "string")).strip().lower()
        if field_type not in _VALID_FIELD_TYPES:
            allowed_types = ", ".join(sorted(_VALID_FIELD_TYPES))
            raise ValueError(
                f"Metadata field '{name}' has invalid type '{field_type}'. "
                f"Allowed types: {allowed_types}."
            )

        description_obj = raw_field.get("description")
        description = (
            description_obj.strip()
            if isinstance(description_obj, str) and description_obj.strip()
            else f"Metadata field '{name}'."
        )
        required = bool(raw_field.get("required", False))

        source = str(raw_field.get("source", "entities")).strip().lower()
        if source not in {"runtime", "entities"}:
            raise ValueError(
                f"Metadata field '{name}' has invalid source '{source}'. "
                "Use 'runtime' or 'entities'."
            )

        normalized: dict[str, Any] = {
            "name": name,
            "type": field_type,
            "required": required,
            "description": description,
            "source": source,
        }

        if source == "runtime":
            runtime = str(raw_field.get("runtime", "")).strip().lower()
            if runtime not in _VALID_RUNTIME_FIELDS:
                allowed_runtime = ", ".join(sorted(_VALID_RUNTIME_FIELDS))
                raise ValueError(
                    f"Metadata field '{name}' has invalid runtime source '{runtime}'. "
                    f"Allowed runtime values: {allowed_runtime}."
                )
            normalized["runtime"] = runtime
            normalized["mode"] = "runtime"
            normalized["source_classes"] = []
            normalized["contains_any"] = []
            normalized_fields.append(normalized)
            continue

        source_classes = _normalize_source_classes(raw_field)
        if not source_classes:
            raise ValueError(
                f"Metadata field '{name}' requires 'source_class' or "
                "'source_classes' for entity extraction."
            )

        requested_mode = raw_field.get("mode")
        mode = _normalize_field_mode(requested_mode, field_type=field_type)
        contains_any = _normalize_contains_any(
            raw_field.get("contains_any"),
            mode=mode,
            field_name=name,
        )

        normalized["source_classes"] = source_classes
        normalized["mode"] = mode
        normalized["contains_any"] = contains_any
        normalized_fields.append(normalized)

    normalized_profile: dict[str, Any] = {
        "name": str(raw.get("name", "langextract_profile")),
        "description": str(
            raw.get("description", "User-defined langextract metadata profile.")
        ),
        "prompt_description": prompt_description,
        "fields": normalized_fields,
    }
    if max_chars is not None:
        normalized_profile["max_chars"] = max_chars
    return normalized_profile


def langextract_schema_fields(
    profile: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return schema field definitions for langextract metadata."""
    normalized = normalize_langextract_profile(profile)
    fields: list[dict[str, Any]] = []
    for field in normalized["fields"]:
        fields.append(
            {
                "name": field["name"],
                "type": field["type"],
                "required": bool(field.get("required", False)),
                "description": str(field.get("description", "")),
            }
        )
    return fields


def langextract_field_names(profile: dict[str, Any] | None = None) -> set[str]:
    """Return field names used by langextract metadata extraction."""
    return {field["name"] for field in langextract_schema_fields(profile)}


def ensure_langextract_schema_fields(
    schema_def: dict[str, Any],
    profile: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    """Ensure schema contains langextract field definitions."""
    normalized_profile = normalize_langextract_profile(
        profile if profile is not None else _schema_profile_if_present(schema_def)
    )
    required_fields = langextract_schema_fields(normalized_profile)

    fields_obj = schema_def.get("fields")
    fields: list[dict[str, Any]]
    if isinstance(fields_obj, list):
        fields = [dict(field) for field in fields_obj if isinstance(field, dict)]
    else:
        fields = []

    existing_names = {
        str(field.get("name")) for field in fields if isinstance(field.get("name"), str)
    }
    updated = list(fields)
    changed = False
    for field in required_fields:
        if field["name"] in existing_names:
            continue
        updated.append(dict(field))
        changed = True

    merged = dict(schema_def)
    if changed:
        merged["fields"] = updated

    existing_profile = _schema_profile_if_present(schema_def)
    if profile is not None or existing_profile is not None:
        if existing_profile != normalized_profile:
            merged["metadata_profile"] = normalized_profile
            changed = True
        elif "metadata_profile" in schema_def:
            merged["metadata_profile"] = existing_profile

    return merged, changed


def extract_metadata(
    *,
    file_path: str,
    root_path: str,
    content: str,
    schema_def: dict[str, Any] | None = None,
    with_langextract: bool = False,
    langextract_model_id: str | None = None,
    langextract_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build metadata used for filtering and schema-aware indexing.

    If a schema is provided with a `fields` list, only those keys are emitted.
    """
    absolute_path = str(Path(file_path).resolve())
    relative_path = os.path.relpath(absolute_path, str(Path(root_path).resolve()))
    extension = Path(file_path).suffix.lower()

    stat = os.stat(file_path)
    metadata: dict[str, Any] = {
        "filename": Path(file_path).name,
        "relative_path": relative_path,
        "extension": extension,
        "document_type": infer_document_type(file_path),
        "file_size_bytes": int(stat.st_size),
        "file_mtime": float(stat.st_mtime),
        "mentions_currency": bool(_CURRENCY_RE.search(content)),
        "mentions_dates": bool(_DATE_RE.search(content)),
    }
    if with_langextract:
        resolved_profile = _resolve_langextract_profile(
            schema_def=schema_def,
            profile_override=langextract_profile,
        )
        metadata.update(
            _extract_langextract_metadata(
                content=content,
                model_id=langextract_model_id,
                profile=resolved_profile,
            )
        )

    if not schema_def:
        return metadata

    fields = schema_def.get("fields")
    if not isinstance(fields, list):
        return metadata

    allowed: set[str] = set()
    for field in fields:
        if isinstance(field, dict):
            name = field.get("name")
            if isinstance(name, str):
                allowed.add(name)

    if not allowed:
        return metadata

    return {k: v for k, v in metadata.items() if k in allowed}


def _extract_langextract_metadata(
    *,
    content: str,
    model_id: str | None = None,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_profile = normalize_langextract_profile(profile)
    defaults = _profile_defaults(normalized_profile)

    api_key = (
        os.getenv("LANGEXTRACT_API_KEY")
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
    )
    if not api_key:
        return defaults

    try:
        import langextract as lx  # type: ignore[import-not-found]
    except Exception:
        return defaults

    profile_max_chars_obj = normalized_profile.get("max_chars")
    profile_max_chars = (
        _safe_positive_int(
            profile_max_chars_obj,
            minimum=500,
            field_name="max_chars",
        )
        if profile_max_chars_obj is not None
        else None
    )
    max_chars = profile_max_chars or _safe_int_env(
        "FS_EXPLORER_LANGEXTRACT_MAX_CHARS",
        default=6000,
        minimum=500,
    )
    snippet = content[:max_chars]
    if not snippet.strip():
        return defaults

    effective_model_id = model_id or os.getenv(
        "FS_EXPLORER_LANGEXTRACT_MODEL",
        "gemini-3-flash-preview",
    )
    try:
        result = lx.extract(
            text_or_documents=snippet,
            prompt_description=str(normalized_profile["prompt_description"]),
            examples=_langextract_examples(lx),
            model_id=effective_model_id,
            api_key=api_key,
            max_char_buffer=min(1200, max_chars),
            show_progress=False,
            prompt_validation_level=lx.prompt_validation.PromptValidationLevel.OFF,
        )
    except Exception:
        return defaults

    extractions = list(result.extractions or [])
    return _aggregate_profile_metadata(
        normalized_profile=normalized_profile,
        extractions=extractions,
        enabled=True,
    )


def _schema_profile_if_present(schema_def: dict[str, Any] | None) -> dict[str, Any] | None:
    if not schema_def:
        return None
    metadata_profile = schema_def.get("metadata_profile")
    if isinstance(metadata_profile, dict):
        return metadata_profile
    return None


def _resolve_langextract_profile(
    *,
    schema_def: dict[str, Any] | None,
    profile_override: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if profile_override is not None:
        return profile_override
    return _schema_profile_if_present(schema_def)


def _normalize_source_classes(raw_field: dict[str, Any]) -> list[str]:
    classes: list[str] = []
    single = raw_field.get("source_class")
    if isinstance(single, str) and single.strip():
        classes.append(single.strip().lower())

    multi = raw_field.get("source_classes")
    if isinstance(multi, list):
        for item in multi:
            if isinstance(item, str) and item.strip():
                classes.append(item.strip().lower())

    seen: set[str] = set()
    deduped: list[str] = []
    for class_name in classes:
        if class_name in seen:
            continue
        seen.add(class_name)
        deduped.append(class_name)
    return deduped


def _normalize_field_mode(mode_obj: Any, *, field_type: str) -> str:
    if isinstance(mode_obj, str) and mode_obj.strip():
        requested = mode_obj.strip().lower()
        normalized = _FIELD_MODE_ALIASES.get(requested)
        if normalized is None:
            allowed = ", ".join(sorted(set(_FIELD_MODE_ALIASES.values())))
            raise ValueError(
                f"Unsupported metadata field mode '{requested}'. "
                f"Allowed modes: {allowed}."
            )
        return normalized

    if field_type == "boolean":
        return "exists"
    if field_type in {"integer", "number"}:
        return "count"
    return "values"


def _normalize_contains_any(
    contains_obj: Any,
    *,
    mode: str,
    field_name: str,
) -> list[str]:
    if mode != "contains":
        return []
    if not isinstance(contains_obj, list) or not contains_obj:
        raise ValueError(
            f"Metadata field '{field_name}' with mode 'contains' "
            "requires 'contains_any' list."
        )
    terms: list[str] = []
    for term in contains_obj:
        if isinstance(term, str) and term.strip():
            terms.append(term.strip().lower())
    if not terms:
        raise ValueError(
            f"Metadata field '{field_name}' with mode 'contains' "
            "has no valid 'contains_any' terms."
        )
    return terms


def _profile_defaults(profile: dict[str, Any]) -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    for field in profile["fields"]:
        defaults[field["name"]] = _default_field_value(field)
    return defaults


def _default_field_value(field: dict[str, Any]) -> Any:
    source = str(field.get("source", "entities"))
    runtime = str(field.get("runtime", ""))
    if source == "runtime":
        if runtime == "enabled":
            return False
        if runtime == "extraction_count":
            return 0
        if runtime == "entity_classes":
            return ""

    field_type = str(field.get("type", "string"))
    if field_type == "boolean":
        return False
    if field_type == "integer":
        return 0
    if field_type == "number":
        return 0.0
    return ""


def _aggregate_profile_metadata(
    *,
    normalized_profile: dict[str, Any],
    extractions: list[Any],
    enabled: bool,
) -> dict[str, Any]:
    classes: set[str] = set()
    by_class: dict[str, list[str]] = defaultdict(list)

    for extraction in extractions:
        extraction_class = str(getattr(extraction, "extraction_class", "")).strip().lower()
        extraction_text = str(getattr(extraction, "extraction_text", "")).strip()
        if not extraction_class:
            continue
        classes.add(extraction_class)
        if extraction_text:
            by_class[extraction_class].append(extraction_text)

    metadata: dict[str, Any] = {}
    for field in normalized_profile["fields"]:
        name = str(field["name"])
        source = str(field["source"])
        if source == "runtime":
            value = _runtime_field_value(
                field=field,
                enabled=enabled,
                extraction_count=len(extractions),
                classes=classes,
            )
            metadata[name] = _coerce_field_value(
                value=value,
                field_type=str(field["type"]),
            )
            continue

        matched_values: list[str] = []
        for extraction_class in field["source_classes"]:
            matched_values.extend(by_class.get(extraction_class, []))
        value = _entity_field_value(field=field, matched_values=matched_values)
        metadata[name] = _coerce_field_value(value=value, field_type=str(field["type"]))

    defaults = _profile_defaults(normalized_profile)
    for key, default_value in defaults.items():
        metadata.setdefault(key, default_value)
    return metadata


def _runtime_field_value(
    *,
    field: dict[str, Any],
    enabled: bool,
    extraction_count: int,
    classes: set[str],
) -> Any:
    runtime = str(field.get("runtime", ""))
    if runtime == "enabled":
        return enabled
    if runtime == "extraction_count":
        return extraction_count
    if runtime == "entity_classes":
        return ", ".join(sorted(classes))
    return _default_field_value(field)


def _entity_field_value(*, field: dict[str, Any], matched_values: list[str]) -> Any:
    mode = str(field.get("mode", "values"))
    if mode == "count":
        return len(matched_values)
    if mode == "exists":
        return bool(matched_values)
    if mode == "contains":
        terms = [str(term).lower() for term in field.get("contains_any", [])]
        lowered_values = [value.lower() for value in matched_values]
        return any(term in value for term in terms for value in lowered_values)
    deduped = _dedupe_preserve_order(matched_values)
    return ", ".join(deduped)


def _coerce_field_value(*, value: Any, field_type: str) -> Any:
    if field_type == "boolean":
        return bool(value)
    if field_type == "integer":
        if isinstance(value, bool):
            return int(value)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
    if field_type == "number":
        if isinstance(value, bool):
            return float(int(value))
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
    if value is None:
        return ""
    return str(value)


def _langextract_examples(lx: Any) -> list[Any]:
    return [
        lx.data.ExampleData(
            text=(
                "TechCorp Industries will pay $45,000,000 in cash consideration, "
                "with a $1,500,000 escrow reserve and a $5,000,000 earnout to "
                "acquire StartupXYZ LLC. CTO Dr. Sarah Chen signed on January 15, 2025."
            ),
            extractions=[
                lx.data.Extraction(
                    extraction_class="organization",
                    extraction_text="TechCorp Industries",
                ),
                lx.data.Extraction(
                    extraction_class="organization",
                    extraction_text="StartupXYZ LLC",
                ),
                lx.data.Extraction(
                    extraction_class="money",
                    extraction_text="$45,000,000",
                ),
                lx.data.Extraction(
                    extraction_class="money",
                    extraction_text="$1,500,000",
                ),
                lx.data.Extraction(
                    extraction_class="money",
                    extraction_text="$5,000,000",
                ),
                lx.data.Extraction(
                    extraction_class="deal_term",
                    extraction_text="cash consideration",
                ),
                lx.data.Extraction(
                    extraction_class="deal_term",
                    extraction_text="escrow reserve",
                ),
                lx.data.Extraction(
                    extraction_class="deal_term",
                    extraction_text="earnout",
                ),
                lx.data.Extraction(
                    extraction_class="person",
                    extraction_text="Dr. Sarah Chen",
                ),
                lx.data.Extraction(
                    extraction_class="date",
                    extraction_text="January 15, 2025",
                ),
            ],
        )
    ]


def _dedupe_preserve_order(values: list[str], *, max_items: int = 16) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        key = value.strip()
        if not key:
            continue
        lower = key.lower()
        if lower in seen:
            continue
        seen.add(lower)
        deduped.append(key)
        if len(deduped) >= max_items:
            break
    return deduped


def _safe_positive_int(value: Any, *, minimum: int, field_name: str) -> int:
    try:
        integer = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Metadata profile field '{field_name}' must be an integer."
        ) from exc
    if integer < minimum:
        raise ValueError(
            f"Metadata profile field '{field_name}' must be >= {minimum}."
        )
    return integer


def _safe_int_env(name: str, *, default: int, minimum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= minimum else minimum
