#!/usr/bin/env python
"""Compare reference CP2K trajectories against a DeePMD checkpoint."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import dpdata
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from deepmd.calculator import DP
from matplotlib.colors import LogNorm


mpl.rcParams.update(
    {
        "font.family": "Times New Roman",
        "mathtext.fontset": "stix",
        "font.size": 12,
        "figure.dpi": 250,
    }
)


HARTREE_TO_EV = 27.21138602
HARTREE_BOHR_TO_EV_A = 51.42206717


def parse_xyz_frames(filename: Path, scale: float = 1.0):
    if not filename.exists():
        return None, 0
    content = filename.read_text(encoding="utf-8").splitlines()
    if not content:
        return None, 0
    n_atoms = int(content[0].strip())
    step_size = n_atoms + 2
    frames = []
    for i in range(0, len(content), step_size):
        if not content[i].strip().isdigit() or i + step_size > len(content):
            continue
        block = content[i + 2 : i + step_size]
        frame = [
            [float(val) * scale for val in line.split()[1:4]]
            for line in block
            if len(line.split()) >= 4
        ]
        if len(frame) == n_atoms:
            frames.append(frame)
    return np.array(frames, dtype=float), n_atoms


def parse_energies(filename: Path):
    if not filename.exists():
        return np.array([])
    energies = []
    with filename.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text or text.startswith("#") or "=" in text:
                continue
            parts = text.split()
            if len(parts) >= 5 and parts[0].isdigit():
                try:
                    energies.append(float(parts[4]) * HARTREE_TO_EV)
                except ValueError:
                    continue
    return np.array(energies)


def load_cp2k_labeled_system(md_dir: Path):
    pos_file = next((path for path in md_dir.iterdir() if path.name.endswith("-pos-1.xyz")), None)
    if pos_file is None:
        raise FileNotFoundError(f"No *-pos-1.xyz file found in {md_dir}")

    prefix = pos_file.name.replace("-pos-1.xyz", "")
    frc_file = md_dir / f"{prefix}-frc-1.xyz"
    ener_file = md_dir / f"{prefix}-1.ener"

    coords, _ = parse_xyz_frames(pos_file, scale=1.0)
    forces, _ = parse_xyz_frames(frc_file, scale=HARTREE_BOHR_TO_EV_A)
    energies = parse_energies(ener_file)

    if coords is None or forces is None:
        raise RuntimeError(f"Failed to parse positions or forces in {md_dir}")

    frames = min(len(coords), len(forces), len(energies))
    if frames == 0:
        raise RuntimeError(f"No aligned frames found in {md_dir}")

    top_sys = dpdata.System(str(pos_file), fmt="xyz", type_map=["Al", "O"])[0]
    labeled = dpdata.LabeledSystem()
    labeled.data = {
        "atom_names": top_sys.data["atom_names"],
        "atom_numbs": top_sys.data["atom_numbs"],
        "atom_types": top_sys.data["atom_types"],
        "cells": np.tile(top_sys.data["cells"][0], (frames, 1, 1)),
        "coords": coords[:frames],
        "forces": forces[:frames],
        "energies": energies[:frames],
        "orig": np.array([0, 0, 0]),
    }
    return labeled


def predict_system(reference_sys, checkpoint: Path, head: str = ""):
    calc = DP(model=str(checkpoint), head=head) if head else DP(model=str(checkpoint))
    pred_sys = dpdata.LabeledSystem()
    for atoms in reference_sys.to_ase_structure():
        atoms = atoms.copy()
        atoms.calc = calc
        _ = atoms.get_potential_energy()
        _ = atoms.get_forces()
        pred_sys.append(dpdata.LabeledSystem().from_ase_structure(atoms, fmt="ase/structure"))
    return pred_sys


def plot_parity(x, y, xlabel: str, ylabel: str, title: str, save_path: Path, error_label: str):
    fig, ax = plt.subplots(figsize=(4, 4))
    lims = [min(x.min(), y.min()), max(x.max(), y.max())]
    if "Force" in title:
        max_force = max(abs(x.min()), abs(x.max()))
        lims = [-max_force, max_force]
    ax.hexbin(
        x,
        y,
        gridsize=80,
        cmap="viridis",
        mincnt=1,
        norm=LogNorm(),
        extent=(lims[0], lims[1], lims[0], lims[1]),
    )
    ax.plot(lims, lims, "k--", lw=0.8, alpha=0.7)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontweight="bold")

    rmse = float(np.sqrt(np.mean((x - y) ** 2)))
    ss_res = float(np.sum((x - y) ** 2))
    ss_tot = float(np.sum((x - np.mean(x)) ** 2))
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot else float("nan")
    ax.text(
        0.05,
        0.95,
        f"$R^2$: {r2:.4f}\nRMSE: {rmse:.4f}",
        transform=ax.transAxes,
        va="top",
        fontsize=11,
        bbox=dict(facecolor="white", alpha=0.7, edgecolor="none"),
    )

    ax_ins = ax.inset_axes([0.60, 0.15, 0.33, 0.25])
    error = y - x
    ax_ins.hist(error, bins=50, color="gray", alpha=0.7, density=True)
    ax_ins.axvline(0.0, color="k", linestyle="--", linewidth=0.8)
    ax_ins.set_yticks([])
    ax_ins.set_xlabel(error_label, fontsize=9)
    ax_ins.tick_params(labelsize=10)

    plt.tight_layout()
    fig.savefig(save_path, dpi=300, bbox_inches="tight", transparent=True)
    plt.close(fig)


def evaluate_system(reference_sys, predicted_sys, skip_frames: int):
    if len(reference_sys) <= skip_frames:
        raise ValueError("Not enough frames after equilibration skip")

    reference_sys = reference_sys[skip_frames:]
    predicted_sys = predicted_sys[skip_frames:]

    num_atoms = int(sum(reference_sys.data["atom_numbs"]))
    e_ref = np.array(reference_sys["energies"]) / num_atoms
    e_pred = np.array(predicted_sys["energies"]) / num_atoms
    f_ref = np.array(reference_sys["forces"])
    f_pred = np.array(predicted_sys["forces"])

    e_ref_centered = e_ref - np.mean(e_ref)
    e_pred_centered = e_pred - np.mean(e_pred)

    metrics = {
        "force_rmse": float(np.sqrt(np.mean((f_pred - f_ref) ** 2))),
        "energy_fluctuation_rmse": float(
            np.sqrt(np.mean((e_pred_centered - e_ref_centered) ** 2))
        ),
    }
    arrays = {
        "force_ref": f_ref.flatten(),
        "force_pred": f_pred.flatten(),
        "energy_ref_centered": e_ref_centered,
        "energy_pred_centered": e_pred_centered,
    }
    return metrics, arrays


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--md-dir", type=Path, action="append", required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--skip-frames", type=int, default=100)
    parser.add_argument("--head", type=str, default="")
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir = output_dir / "metrics"
    plots_dir = output_dir / "plots"
    reports_dir = output_dir / "reports"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    summary_lines = []
    force_metrics = []
    energy_metrics = []
    all_force_ref = []
    all_force_pred = []
    all_energy_ref = []
    all_energy_pred = []

    for md_dir in args.md_dir:
        print(f"Processing {md_dir} ...")
        reference_sys = load_cp2k_labeled_system(md_dir.resolve())
        predicted_sys = predict_system(reference_sys, args.checkpoint.resolve(), head=args.head)
        metrics, arrays = evaluate_system(reference_sys, predicted_sys, args.skip_frames)

        system_name = os.path.basename(md_dir.resolve())
        summary_lines.append(
            f"{system_name}: force_rmse={metrics['force_rmse']:.6f}, "
            f"energy_fluctuation_rmse={metrics['energy_fluctuation_rmse']:.6f}"
        )
        force_metrics.append({"system": system_name, "force_rmse": metrics["force_rmse"]})
        energy_metrics.append(
            {
                "system": system_name,
                "energy_fluctuation_rmse": metrics["energy_fluctuation_rmse"],
            }
        )
        all_force_ref.append(arrays["force_ref"])
        all_force_pred.append(arrays["force_pred"])
        all_energy_ref.append(arrays["energy_ref_centered"])
        all_energy_pred.append(arrays["energy_pred_centered"])

    force_ref = np.concatenate(all_force_ref)[::10]
    force_pred = np.concatenate(all_force_pred)[::10]
    energy_ref = np.concatenate(all_energy_ref)[::10]
    energy_pred = np.concatenate(all_energy_pred)[::10]

    plot_parity(
        force_ref,
        force_pred,
        xlabel=r"$f_{\mathrm{DFT}}$ (eV/A)",
        ylabel=r"$f_{\mathrm{MLP}}$ (eV/A)",
        title="Force Parity",
        save_path=plots_dir / "force_parity.png",
        error_label="Error (eV/A)",
    )
    plot_parity(
        energy_ref,
        energy_pred,
        xlabel=r"$\Delta E_{\mathrm{DFT}}$ (eV/atom)",
        ylabel=r"$\Delta E_{\mathrm{MLP}}$ (eV/atom)",
        title="Energy Fluctuation Parity",
        save_path=plots_dir / "energy_delta.png",
        error_label="Error (eV/atom)",
    )

    overall_force_rmse = float(np.sqrt(np.mean((force_pred - force_ref) ** 2)))
    overall_energy_rmse = float(np.sqrt(np.mean((energy_pred - energy_ref) ** 2)))

    force_payload = {
        "checkpoint_path": str(args.checkpoint.resolve()),
        "skip_frames": args.skip_frames,
        "systems": force_metrics,
        "overall_force_rmse_downsampled": overall_force_rmse,
    }
    energy_payload = {
        "checkpoint_path": str(args.checkpoint.resolve()),
        "skip_frames": args.skip_frames,
        "systems": energy_metrics,
        "overall_energy_fluctuation_rmse_downsampled": overall_energy_rmse,
    }

    (metrics_dir / "force_metrics.json").write_text(
        json.dumps(force_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (metrics_dir / "energy_fluctuation_metrics.json").write_text(
        json.dumps(energy_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (metrics_dir / "metrics_summary.txt").write_text(
        "\n".join(summary_lines) + "\n", encoding="utf-8"
    )

    report_lines = [
        "# OOD Summary",
        "",
        "## Inputs",
        "",
        f"- Checkpoint: `{args.checkpoint.resolve()}`",
        f"- Skip frames: `{args.skip_frames}`",
        f"- Systems: `{len(force_metrics)}`",
        "",
        "## Metrics",
        "",
        f"- Overall force RMSE (downsampled parity arrays): `{overall_force_rmse:.6f}`",
        f"- Overall energy fluctuation RMSE (downsampled parity arrays): `{overall_energy_rmse:.6f}`",
        "",
        "## Per-System Summary",
        "",
    ]
    report_lines.extend([f"- {line}" for line in summary_lines])
    report_lines.extend(
        [
            "",
            "## Remaining Risk",
            "",
            "- This example report summarizes metric evidence only.",
            "- Promotion or deployment decisions still require project-specific thresholds and approval.",
        ]
    )
    (reports_dir / "ood_summary.md").write_text(
        "\n".join(report_lines) + "\n", encoding="utf-8"
    )
    print(f"Done. Results written under: {output_dir}")


if __name__ == "__main__":
    main()
