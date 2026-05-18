from __future__ import annotations

import json
import sys
from pathlib import Path

MCP_SRC = Path(__file__).resolve().parents[1] / "mlpcopilot" / "mcps" / "mlp_dataset_mcp" / "src"
sys.path.insert(0, str(MCP_SRC))

from mlp_dataset_mcp.dataset import DatasetBackend  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _deepmd_raw_system(root: Path) -> Path:
    system = root / "sys_000"
    _write(system / "type.raw", "0 1\n")
    _write(system / "type_map.raw", "H O\n")
    _write(system / "coord.raw", "0 0 0 1 0 0\n0 0 0 1 0.1 0\n")
    _write(system / "force.raw", "0 0 0 0 0 0\n0.1 0 0 -0.1 0 0\n")
    _write(system / "energy.raw", "-1.0\n-1.1\n")
    _write(system / "box.raw", "1 0 0 0 1 0 0 0 1\n1 0 0 0 1 0 0 0 1\n")
    return system


def test_mlp_dataset_mcp_inspects_and_validates_deepmd_raw(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    system = _deepmd_raw_system(dataset)

    inspected = json.loads(DatasetBackend().inspect_dataset(str(dataset)))
    validated = json.loads(DatasetBackend().validate_dataset_integrity(str(dataset)))

    assert inspected["status"] == "success"
    assert inspected["metrics"]["format"] == "deepmd_raw"
    assert inspected["metrics"]["deepmd_raw_systems"][0]["path"] == str(system)
    assert inspected["metrics"]["deepmd_raw_systems"][0]["frames"] == 2
    assert validated["status"] == "success"
    check = next(item for item in validated["metrics"]["checks"] if item["kind"] == "deepmd_raw_system")
    assert check["natoms"] == 2
    assert check["frames"] == 2
    assert check["errors"] == []


def test_mlp_dataset_mcp_detects_deepmd_frame_mismatch(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    system = _deepmd_raw_system(dataset)
    _write(system / "force.raw", "0 0 0 0 0 0\n")

    payload = json.loads(DatasetBackend().validate_dataset_integrity(str(dataset)))

    assert payload["status"] == "failed"
    assert any("force.raw has 1 frames, expected 2" in item for item in payload["errors"])


def test_mlp_dataset_mcp_validates_simple_schema(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    _deepmd_raw_system(dataset)
    schema = tmp_path / "schema.json"
    _write(schema, json.dumps({"required_files": ["sys_000/type.raw", "missing.raw"]}))

    payload = json.loads(DatasetBackend().validate_dataset_schema(str(dataset), str(schema)))

    assert payload["status"] == "failed"
    assert payload["metrics"]["missing_files"] == ["missing.raw"]
    assert payload["artifacts"][0]["type"] == "config"


def test_mlp_dataset_mcp_validates_extxyz_and_writes_report(tmp_path: Path) -> None:
    dataset = tmp_path / "frames.extxyz"
    _write(
        dataset,
        "2\n"
        "Properties=species:S:1:pos:R:3 energy=-1.0\n"
        "H 0 0 0\n"
        "O 1 0 0\n",
    )
    report = tmp_path / "reports" / "dataset.md"

    validated = json.loads(DatasetBackend().validate_dataset_integrity(str(dataset)))
    built = json.loads(
        DatasetBackend().build_dataset_validation_report(
            str(dataset),
            output_path=str(report),
        )
    )

    assert validated["status"] == "success"
    assert validated["metrics"]["scope"] == "file_layout_and_basic_integrity_only"
    assert "label_outliers" in validated["metrics"]["not_checked"]
    assert validated["metrics"]["checks"][0]["frames"] == 1
    assert built["status"] == "success"
    assert report.is_file()
    assert built["artifacts"][0]["path"] == str(report)
    report_text = report.read_text(encoding="utf-8")
    assert "Dataset Validation Report" in report_text
    assert "Scope and Limitations" in report_text
    assert "It does not check unit consistency" in report_text
