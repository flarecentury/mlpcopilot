import json
from pathlib import Path

from mlpcopilot.config.schema import Config


EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples" / "config"
SECRET_FIELD_FRAGMENTS = (
    "apikey",
    "api_key",
    "token",
    "authorization",
    "password",
    "secret",
)
ENDPOINT_FIELD_NAMES = ("apibase", "baseurl", "url")


def test_config_examples_validate_against_schema() -> None:
    paths = sorted(EXAMPLES_DIR.glob("*.json"))

    assert paths
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        Config.model_validate(payload)


def test_config_examples_are_sanitized() -> None:
    for path in sorted(EXAMPLES_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))

        for key, value in _walk_string_values(payload):
            assert not value.startswith("/home/"), f"{path} contains a home-local path"
            assert not value.startswith("/storage/"), f"{path} contains a storage-local path"

            normalized_key = key.replace("-", "").replace("_", "").lower()
            if any(fragment in normalized_key for fragment in SECRET_FIELD_FRAGMENTS):
                assert value == "" or value.startswith("${"), f"{path} contains a literal secret"
            if normalized_key in ENDPOINT_FIELD_NAMES and value.startswith("http"):
                assert "example." in value, f"{path} contains a literal endpoint"


def _walk_string_values(obj: object, key: str = "") -> list[tuple[str, str]]:
    if isinstance(obj, str):
        return [(key, obj)]
    if isinstance(obj, dict):
        values: list[tuple[str, str]] = []
        for child_key, child_value in obj.items():
            values.extend(_walk_string_values(child_value, str(child_key)))
        return values
    if isinstance(obj, list):
        values = []
        for child_value in obj:
            values.extend(_walk_string_values(child_value, key))
        return values
    return []
