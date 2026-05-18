from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

MCP_SRC = Path(__file__).resolve().parents[1] / "mlpcopilot" / "mcps" / "mlp_model_eval_mcp" / "src"
sys.path.insert(0, str(MCP_SRC))

from mlp_model_eval_mcp.checkpoint import ModelEvalBackend  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class _FakeArray(list):
    def tolist(self):
        return list(self)


class _FakeAtoms:
    def __init__(self, formula: str = "H2", natoms: int = 2, energy: float = -1.5) -> None:
        self.calc = None
        self.formula = formula
        self.natoms = natoms
        self.energy = energy

    def __len__(self) -> int:
        return self.natoms

    def get_potential_energy(self) -> float:
        return self.energy

    def get_forces(self):
        return _FakeArray([_FakeArray([0.1, 0.0, 0.0]) for _ in range(self.natoms)])

    def get_stress(self):
        return _FakeArray([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

    def get_chemical_formula(self) -> str:
        return self.formula

    def get_pbc(self):
        return _FakeArray([False, False, False])

    def get_cell(self):
        return _FakeArray([_FakeArray([0.0, 0.0, 0.0]) for _ in range(3)])


def _install_fake_ase_deepmd(monkeypatch) -> None:
    ase = types.ModuleType("ase")
    ase_io = types.ModuleType("ase.io")
    ase_calculators = types.ModuleType("ase.calculators")
    ase_singlepoint = types.ModuleType("ase.calculators.singlepoint")
    deepmd = types.ModuleType("deepmd")
    deepmd_calculator = types.ModuleType("deepmd.calculator")

    def fake_read(path: str, index=None, format=None):
        name = Path(path).stem
        atoms = _FakeAtoms(formula=name or "H2", natoms=2, energy=-float(len(name) or 1))
        if index == ":":
            return [atoms]
        return atoms

    def fake_write(path: str, atoms, format=None, append=False):
        mode = "a" if append else "w"
        with open(path, mode, encoding="utf-8") as handle:
            handle.write(f"{atoms.get_chemical_formula()} {atoms.get_potential_energy()}\n")

    class FakeSinglePointCalculator:
        def __init__(self, atoms, **kwargs) -> None:
            self.atoms = atoms
            self.results = kwargs

    class FakeDP:
        def __init__(self, model: str, head: str | None = None) -> None:
            self.model = model
            self.head = head

    ase_io.read = fake_read
    ase_io.write = fake_write
    ase_singlepoint.SinglePointCalculator = FakeSinglePointCalculator
    deepmd_calculator.DP = FakeDP
    monkeypatch.setitem(sys.modules, "ase", ase)
    monkeypatch.setitem(sys.modules, "ase.io", ase_io)
    monkeypatch.setitem(sys.modules, "ase.calculators", ase_calculators)
    monkeypatch.setitem(sys.modules, "ase.calculators.singlepoint", ase_singlepoint)
    monkeypatch.setitem(sys.modules, "deepmd", deepmd)
    monkeypatch.setitem(sys.modules, "deepmd.calculator", deepmd_calculator)


def test_mlp_model_eval_mcp_inspects_checkpoint_file(tmp_path: Path) -> None:
    checkpoint = tmp_path / "frozen_model.pb"
    _write(checkpoint, "checkpoint-bytes")

    payload = json.loads(ModelEvalBackend().inspect_checkpoint(str(checkpoint)))

    assert payload["status"] == "success"
    assert payload["metrics"]["format"] == "tensorflow_frozen_model"
    assert payload["metrics"]["sha256"]
    assert payload["metrics"]["size_bytes"] == len("checkpoint-bytes")


def test_mlp_model_eval_mcp_uses_deepmd_v3_model_suffixes(tmp_path: Path) -> None:
    checkpoint = tmp_path / "frozen_model.pte"
    _write(checkpoint, "checkpoint-bytes")

    payload = json.loads(ModelEvalBackend().inspect_checkpoint(str(checkpoint)))

    assert payload["status"] == "success"
    assert payload["metrics"]["format"] == "pytorch_exportable_model"


def test_mlp_model_eval_mcp_blocks_without_metrics_artifact(tmp_path: Path) -> None:
    checkpoint = tmp_path / "frozen_model.pb"
    dataset = tmp_path / "dataset"
    _write(checkpoint, "checkpoint-bytes")
    dataset.mkdir()

    payload = json.loads(
        ModelEvalBackend().validate_checkpoint_on_dataset(
            str(checkpoint),
            str(dataset),
        )
    )

    assert payload["status"] == "blocked"
    assert payload["metrics"]["inference_executed"] is False
    assert "No metric_config_path" in payload["warnings"][0]


def test_mlp_model_eval_mcp_checks_precomputed_metrics(tmp_path: Path) -> None:
    checkpoint = tmp_path / "frozen_model.pb"
    dataset = tmp_path / "dataset"
    config = tmp_path / "metrics.json"
    _write(checkpoint, "checkpoint-bytes")
    dataset.mkdir()
    _write(
        config,
        json.dumps(
            {
                "metrics": {"energy_rmse": 0.01, "force_rmse": 0.2},
                "acceptance_criteria": {
                    "energy_rmse": {"max": 0.02},
                    "force_rmse": {"max": 0.1},
                },
            }
        ),
    )

    payload = json.loads(
        ModelEvalBackend().validate_checkpoint_on_dataset(
            str(checkpoint),
            str(dataset),
            metric_config_path=str(config),
        )
    )

    assert payload["status"] == "failed"
    assert payload["metrics"]["checked_metrics"]["force_rmse"] == 0.2
    assert any("force_rmse" in item for item in payload["metrics"]["acceptance"]["failures"])
    assert payload["metrics"]["inference_executed"] is False


def test_mlp_model_eval_mcp_builds_and_compares_metrics(tmp_path: Path) -> None:
    checkpoint_a = tmp_path / "a.pb"
    checkpoint_b = tmp_path / "b.pb"
    dataset = tmp_path / "dataset"
    metrics = tmp_path / "metrics.json"
    compare_config = tmp_path / "compare.json"
    normalized = tmp_path / "normalized.json"
    _write(checkpoint_a, "a")
    _write(checkpoint_b, "b")
    dataset.mkdir()
    _write(metrics, json.dumps({"metrics": {"force_rmse": 0.12}}))
    _write(
        compare_config,
        json.dumps(
            {
                "primary_metric": "force_rmse",
                "checkpoints": {
                    "a": {"path": str(checkpoint_a), "metrics": {"force_rmse": 0.12}},
                    "b": {"path": str(checkpoint_b), "metrics": {"force_rmse": 0.08}},
                },
            }
        ),
    )

    built = json.loads(
        ModelEvalBackend().build_checkpoint_metrics(
            str(metrics),
            checkpoint_path=str(checkpoint_a),
            dataset_path=str(dataset),
            output_path=str(normalized),
        )
    )
    compared = json.loads(
        ModelEvalBackend().compare_checkpoints(
            str(checkpoint_a),
            str(checkpoint_b),
            dataset_path=str(dataset),
            metric_config_path=str(compare_config),
        )
    )

    assert built["status"] == "success"
    assert normalized.is_file()
    assert built["metrics"]["metrics"]["force_rmse"] == 0.12
    assert compared["status"] == "success"
    assert compared["metrics"]["comparison"]["lower_is_better_best"] == "checkpoint_b"
    delta = compared["metrics"]["comparison"]["delta_b_minus_a"]["force_rmse"]
    assert abs(delta + 0.04) < 1e-12


def test_mlp_model_eval_mcp_builds_checkpoint_benchmark_report(tmp_path: Path) -> None:
    checkpoint = tmp_path / "frozen_model.pb"
    dataset = tmp_path / "dataset"
    metrics = tmp_path / "dp_test_metrics.json"
    report = tmp_path / "reports" / "checkpoint.md"
    _write(checkpoint, "checkpoint-bytes")
    _write(dataset / "set.000" / "energy.npy", "fake-energy")
    _write(
        metrics,
        json.dumps(
            {
                "metrics": {"energy_rmse": 0.01, "force_rmse": 0.08},
                "acceptance_criteria": {
                    "energy_rmse": {"max": 0.02},
                    "force_rmse": {"max": 0.1},
                },
                "command": ["dp", "test", "-m", str(checkpoint)],
            }
        ),
    )

    payload = json.loads(
        ModelEvalBackend().build_checkpoint_benchmark_report(
            metrics_path=str(metrics),
            checkpoint_path=str(checkpoint),
            dataset_path=str(dataset),
            output_path=str(report),
        )
    )

    assert payload["status"] == "success"
    assert payload["metrics"]["metric_count"] == 2
    assert payload["metrics"]["acceptance"]["failures"] == []
    assert payload["metrics"]["checkpoint"]["sha256"]
    assert payload["metrics"]["dataset"]["file_count"] == 1
    assert any(item["type"] == "report" and item["path"] == str(report) for item in payload["artifacts"])
    content = report.read_text(encoding="utf-8")
    assert "Checkpoint Benchmark Report" in content
    assert "force_rmse" in content
    assert "does not declare the checkpoint production-ready" in content


def test_mlp_model_eval_mcp_builds_benchmark_plots_and_links_report(tmp_path: Path) -> None:
    checkpoint = tmp_path / "frozen_model.pb"
    dataset = tmp_path / "dataset"
    metrics = tmp_path / "dp_test_metrics.json"
    detail_prefix = tmp_path / "dp_test_detail"
    plots_dir = tmp_path / "plots"
    report = tmp_path / "reports" / "checkpoint.md"
    _write(checkpoint, "checkpoint-bytes")
    _write(dataset / "set.000" / "energy.npy", "fake-energy")
    _write(
        detail_prefix.with_suffix(".e.out"),
        "data_e pred_e\n"
        "-1.00 -0.95\n"
        "-0.50 -0.55\n"
        "-0.25 -0.20\n",
    )
    _write(
        detail_prefix.with_suffix(".f.out"),
        "data_fx data_fy data_fz pred_fx pred_fy pred_fz\n"
        "0.00 0.10 0.20 0.01 0.08 0.25\n"
        "0.30 0.40 0.50 0.28 0.42 0.55\n",
    )
    _write(
        metrics,
        json.dumps(
            {
                "metrics": {"energy_rmse": 0.05, "force_rmse": 0.04},
                "detail_prefix": str(detail_prefix),
            }
        ),
    )

    plotted = json.loads(
        ModelEvalBackend().build_benchmark_plots(
            metrics_path=str(metrics),
            output_dir=str(plots_dir),
        )
    )
    linked = json.loads(
        ModelEvalBackend().build_checkpoint_benchmark_report(
            metrics_path=str(metrics),
            checkpoint_path=str(checkpoint),
            dataset_path=str(dataset),
            output_path=str(report),
            plot_paths=plotted["metrics"]["plot_paths"],
        )
    )

    assert plotted["status"] == "success"
    assert plotted["metrics"]["plot_count"] == 5
    assert plotted["metrics"]["energy_point_count"] == 3
    assert plotted["metrics"]["force_component_count"] == 6
    for path_text in plotted["metrics"]["plot_paths"]:
        path = Path(path_text)
        assert path.is_file()
        assert path.read_bytes().startswith(b"\x89PNG")
    assert linked["status"] == "success"
    assert any(item["type"] == "plot" for item in linked["artifacts"])
    content = report.read_text(encoding="utf-8")
    assert "## Plots" in content
    assert "energy_parity.png" in content
    assert "force_components.png" in content


def test_mlp_model_eval_mcp_runs_deepmd_v3_dp_test_command(tmp_path: Path) -> None:
    checkpoint = tmp_path / "frozen_model.pte"
    dataset = tmp_path / "dataset"
    output_dir = tmp_path / "out"
    fake_dp = tmp_path / "fake_dp.py"
    _write(checkpoint, "checkpoint-bytes")
    dataset.mkdir()
    _write(
        fake_dp,
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import pathlib\n"
        "import sys\n"
        "args = sys.argv[1:]\n"
        "detail = pathlib.Path(args[args.index('--detail-file') + 1])\n"
        "detail.with_suffix('.e.out').write_text('data_e pred_e\\n', encoding='utf-8')\n"
        "pathlib.Path('argv.json').write_text(json.dumps(args), encoding='utf-8')\n"
        "print('Energy RMSE        : 1.500000e-02 eV')\n"
        "print('Energy RMSE/Natoms : 5.000000e-03 eV')\n"
        "print('Force  RMSE        : 2.500000e-01 eV/Å')\n",
    )
    os.chmod(fake_dp, 0o755)

    payload = json.loads(
        ModelEvalBackend().run_deepmd_test(
            checkpoint_path=str(checkpoint),
            dataset_path=str(dataset),
            data_source="system",
            dp_command=str(fake_dp),
            backend="pytorch-exportable",
            numb_test=3,
            shuffle_test=True,
            atomic=True,
            head="energy",
            output_dir=str(output_dir),
            timeout_seconds=5,
        )
    )

    assert payload["status"] == "success"
    assert payload["metrics"]["inference_executed"] is True
    assert payload["metrics"]["metrics"]["energy_rmse"] == 0.015
    assert payload["metrics"]["metrics"]["force_rmse"] == 0.25
    assert (output_dir / "dp_test_metrics.json").is_file()
    assert (output_dir / "dp_test_detail.e.out").is_file()
    argv = json.loads((output_dir / "argv.json").read_text(encoding="utf-8"))
    assert argv[:3] == ["--backend", "pytorch-exportable", "test"]
    assert "--head" in argv
    assert "--shuffle-test" in argv
    assert "--atomic" in argv


def test_mlp_model_eval_mcp_can_run_deepmd_test_during_validation(tmp_path: Path) -> None:
    checkpoint = tmp_path / "frozen_model.pb"
    dataset = tmp_path / "dataset"
    output_dir = tmp_path / "out"
    fake_dp = tmp_path / "fake_dp.py"
    _write(checkpoint, "checkpoint-bytes")
    dataset.mkdir()
    _write(
        fake_dp,
        "#!/usr/bin/env python3\n"
        "import pathlib\n"
        "import sys\n"
        "args = sys.argv[1:]\n"
        "detail = pathlib.Path(args[args.index('--detail-file') + 1])\n"
        "detail.with_suffix('.f.out').write_text('data_f pred_f\\n', encoding='utf-8')\n"
        "print('Force  RMSE        : 8.000000e-02 eV/Å')\n",
    )
    os.chmod(fake_dp, 0o755)

    payload = json.loads(
        ModelEvalBackend().validate_checkpoint_on_dataset(
            str(checkpoint),
            str(dataset),
            run_if_metrics_missing=True,
            dp_command=str(fake_dp),
            output_dir=str(output_dir),
            timeout_seconds=5,
        )
    )

    assert payload["status"] == "success"
    assert payload["metrics"]["checked_metrics"]["force_rmse"] == 0.08
    assert payload["metrics"]["inference_executed"] is True


def test_mlp_model_eval_mcp_predicts_one_ase_structure(tmp_path: Path, monkeypatch) -> None:
    _install_fake_ase_deepmd(monkeypatch)
    checkpoint = tmp_path / "frozen_model.pte"
    structure = tmp_path / "water.xyz"
    output = tmp_path / "prediction.json"
    extxyz = tmp_path / "prediction.extxyz"
    _write(checkpoint, "checkpoint-bytes")
    _write(structure, "2\nwater\nH 0 0 0\nH 0 0 1\n")

    payload = json.loads(
        ModelEvalBackend().predict_energy_force(
            structure_path=str(structure),
            checkpoint_path=str(checkpoint),
            output_path=str(output),
            extxyz_path=str(extxyz),
            head="energy",
        )
    )

    assert payload["status"] == "success"
    assert payload["metrics"]["formula"] == "water"
    assert payload["metrics"]["natoms"] == 2
    assert payload["metrics"]["inference_executed"] is True
    assert payload["metrics"]["forces"] == [[0.1, 0.0, 0.0], [0.1, 0.0, 0.0]]
    assert output.is_file()
    assert extxyz.is_file()
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["checkpoint_sha256"]
    assert written["forces"][0] == [0.1, 0.0, 0.0]


def test_mlp_model_eval_mcp_batch_predicts_ase_structures(tmp_path: Path, monkeypatch) -> None:
    _install_fake_ase_deepmd(monkeypatch)
    checkpoint = tmp_path / "frozen_model.pb"
    structures = tmp_path / "structures"
    output_dir = tmp_path / "batch"
    _write(checkpoint, "checkpoint-bytes")
    _write(structures / "a.xyz", "1\na\nH 0 0 0\n")
    _write(structures / "long.extxyz", "1\nlong\nH 0 0 0\n")

    payload = json.loads(
        ModelEvalBackend().batch_predict(
            structure_dir=str(structures),
            checkpoint_path=str(checkpoint),
            output_dir=str(output_dir),
            max_structures=10,
        )
    )

    assert payload["status"] == "success"
    assert payload["metrics"]["prediction_count"] == 2
    assert payload["metrics"]["attempted_count"] == 2
    assert payload["metrics"]["inference_executed"] is True
    assert (output_dir / "batch_predictions.json").is_file()
    assert (output_dir / "batch_predictions.extxyz").is_file()
    batch = json.loads((output_dir / "batch_predictions.json").read_text(encoding="utf-8"))
    assert len(batch["predictions"]) == 2
