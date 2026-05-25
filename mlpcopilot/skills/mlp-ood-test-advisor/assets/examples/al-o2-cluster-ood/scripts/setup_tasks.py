#!/usr/bin/env python
"""Generate finite-cluster AIMD tasks for the Al/O2 OOD example."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from ase.build import molecule
from ase.cluster import Icosahedron, Octahedron
from ase.io import write
from ase.visualize.plot import plot_atoms


def build_clusters():
    return {
        13: Icosahedron("Al", noshells=2),
        55: Icosahedron("Al", noshells=3),
        79: Octahedron("Al", length=5, cutoff=1),
        147: Icosahedron("Al", noshells=4),
        309: Icosahedron("Al", noshells=5),
    }


def added_mos_for_size(size: int) -> int:
    mapping = {13: 50, 55: 200, 79: 300, 147: 500, 309: 1000}
    return mapping.get(size, 200)


def add_o2_molecules(system, max_pos, min_pos, d_safe: float, num_o2: int):
    max_x, max_y, max_z = max_pos
    min_x, min_y, min_z = min_pos

    if num_o2 >= 1:
        o2 = molecule("O2")
        o2.rotate(90, "x")
        o2.translate((0, 0, max_z + d_safe))
        system += o2
    if num_o2 >= 2:
        o2 = molecule("O2")
        o2.rotate(90, "x")
        o2.translate((0, 0, min_z - d_safe))
        system += o2
    if num_o2 >= 4:
        o2 = molecule("O2")
        o2.rotate(90, "x")
        o2.translate((max_x + d_safe, 0, 0))
        system += o2
        o2 = molecule("O2")
        o2.rotate(90, "x")
        o2.translate((min_x - d_safe, 0, 0))
        system += o2
    if num_o2 >= 6:
        o2 = molecule("O2")
        o2.rotate(90, "y")
        o2.translate((0, max_y + d_safe, 0))
        system += o2
        o2 = molecule("O2")
        o2.rotate(90, "y")
        o2.translate((0, min_y - d_safe, 0))
        system += o2
    return system


def render_structure_png(atoms, output_path: Path, title: str, cell_length: float):
    fig, ax = plt.subplots(figsize=(6, 6))
    plot_atoms(atoms, ax=ax, radii=1.2, rotation="-10x,20y,0z")
    rect = plt.Rectangle(
        (0, 0),
        cell_length,
        cell_length,
        fill=False,
        edgecolor="red",
        linestyle="--",
        alpha=0.5,
    )
    ax.add_patch(rect)
    ax.set_title(title, fontsize=14)
    ax.axis("off")
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--template-path", type=Path, required=True)
    parser.add_argument("--padding", type=float, default=10.0)
    parser.add_argument("--d-safe", type=float, default=3.0)
    parser.add_argument("--steps", type=int, default=6000)
    parser.add_argument(
        "--temperatures",
        type=int,
        nargs="+",
        default=[700, 1200],
        help="Temperature list in K. Defaults to the OOD example windows only.",
    )
    parser.add_argument(
        "--o2-configs",
        type=int,
        nargs="+",
        default=[1, 2, 4, 6],
        help="Number of O2 molecules to place around each cluster.",
    )
    args = parser.parse_args()

    temperatures = sorted(set(args.temperatures))
    o2_configs = sorted(set(args.o2_configs))
    clusters = build_clusters()

    output_root = args.output_root.resolve()
    structure_dir = output_root / "structures"
    task_root = output_root / "tasks"
    structure_dir.mkdir(parents=True, exist_ok=True)
    task_root.mkdir(parents=True, exist_ok=True)
    template = args.template_path.read_text(encoding="utf-8")

    task_manifest = {
        "case_name": "al-o2-cluster-ood",
        "template_path": str(args.template_path.resolve()),
        "output_root": str(output_root),
        "padding": args.padding,
        "d_safe": args.d_safe,
        "steps": args.steps,
        "temperatures_k": temperatures,
        "o2_configs": o2_configs,
        "clusters": [],
        "task_dirs": [],
    }

    print("Generating finite-cluster AIMD example tasks...")
    for size, al_cluster in clusters.items():
        al_cluster.center(about=(0.0, 0.0, 0.0))
        positions = al_cluster.get_positions()
        max_pos = np.max(positions, axis=0)
        min_pos = np.min(positions, axis=0)

        for num_o2 in o2_configs:
            system = add_o2_molecules(
                al_cluster.copy(),
                max_pos=max_pos,
                min_pos=min_pos,
                d_safe=args.d_safe,
                num_o2=num_o2,
            )
            ptp = np.ptp(system.get_positions(), axis=0)
            cell_length = float(np.ceil(np.max(ptp) + args.padding))
            system.set_cell([cell_length, cell_length, cell_length])
            system.center()

            xyz_name = f"Al{size}_{num_o2}O2.xyz"
            xyz_path = structure_dir / xyz_name
            write(xyz_path, system)
            task_manifest["clusters"].append(
                {
                    "cluster_size": size,
                    "o2_count": num_o2,
                    "cell_length": cell_length,
                    "structure_path": str(xyz_path),
                }
            )

            png_name = f"Al{size}_{num_o2}O2_L{int(cell_length)}.png"
            render_structure_png(
                system,
                structure_dir / png_name,
                title=f"Al{size} + {num_o2} O2 | Box: {cell_length:.0f} A (non-PBC)",
                cell_length=cell_length,
            )

            for temp in temperatures:
                task_dir = task_root / f"Al{size}_{num_o2}O2" / f"{temp}K"
                task_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy(xyz_path, task_dir / xyz_name)
                task_manifest["task_dirs"].append(
                    {
                        "cluster_size": size,
                        "o2_count": num_o2,
                        "temperature_k": temp,
                        "task_dir": str(task_dir),
                        "input_path": str(task_dir / "input.inp"),
                    }
                )

                input_text = template
                input_text = input_text.replace(
                    "PROJECT Al_cluster_no_pbc", f"PROJECT Al{size}_{num_o2}O2_{temp}K"
                )
                input_text = input_text.replace(
                    "ABC 20.0 20.0 20.0", f"ABC {cell_length} {cell_length} {cell_length}"
                )
                input_text = input_text.replace(
                    "COORD_FILE_NAME Al_cluster_O2.xyz", f"COORD_FILE_NAME {xyz_name}"
                )
                input_text = input_text.replace("STEPS 6000", f"STEPS {args.steps}")
                input_text = input_text.replace("TEMPERATURE 700", f"TEMPERATURE {temp}")
                input_text = input_text.replace(
                    "ADDED_MOS 200", f"ADDED_MOS {added_mos_for_size(size)}"
                )
                (task_dir / "input.inp").write_text(input_text, encoding="utf-8")

    (output_root / "task_manifest.json").write_text(
        json.dumps(task_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Done. Outputs written under: {output_root}")


if __name__ == "__main__":
    main()
