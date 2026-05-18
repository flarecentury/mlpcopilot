---
name: dpgen-machine-writer
description: Use this skill when writing or reviewing DP-GEN machine.json files for MLP workflows, especially when DeePMD-kit, LAMMPS, CP2K, VASP, ABACUS, or other engines are launched through Apptainer/Singularity SIF wrappers, host MPI, SSHContext, Slurm, PBS, or local Shell execution.
---

# DP-GEN Machine Writer

Use this skill to produce DP-GEN-native `machine.json` files. Do not introduce non-DP-GEN fields such as `toolchain` into the final `machine.json`.

The agent may use a separate note/profile to remember SIF paths, MPI family, queue names, and wrapper paths, but the output consumed by DP-GEN must stay in DP-GEN/DPDispatcher format.

For real projects, prefer adapting an existing local or upstream DP-GEN `machine*.json` reference over starting from an abstract template. Read the complete reference file first, preserve valid site-specific structure, and write a complete JSON output. Do not return abbreviated sections, ellipses, or "fill this in" placeholders unless the user explicitly asks for a sketch.

## Boundary

- Write `machine.json`; do not rewrite DP-GEN.
- Use wrappers for Apptainer/Singularity commands instead of placing long container commands directly in `machine.json`.
- `train.command` normally runs DeePMD-kit `dp`.
- `model_devi.command` normally runs LAMMPS `lmp`, often from the DeePMD-kit image.
- `fp.command` runs CP2K, VASP, ABACUS, PWscf, Gaussian, or a user wrapper.
- Put scientific templates and large inputs in files, not in the chat context.
- Treat high-cost execution as approval-gated; generating `machine.json` is not approval to run.

## Required Sections

Every generated `machine.json` should include:

```json
{
  "api_version": "1.0",
  "deepmd_version": "3.1.3",
  "train": {},
  "model_devi": {},
  "fp": {}
}
```

Each stage should have:

- `command`: the command DPDispatcher runs inside the task directory.
- `machine`: where/how jobs are dispatched.
- `resources`: scheduler and resource settings.
- `user_forward_files`: wrapper scripts or extra files to send to the worker.
- `user_backward_files`: extra outputs to retrieve, if needed.

## Command Rules

Prefer short audited wrappers:

```text
bash wrappers/dp_apptainer.sh
bash wrappers/lmp_apptainer.sh
bash wrappers/cp2k_apptainer.sh -i input.inp -o output.out
bash wrappers/vasp_host.sh
```

Do not write long fragile commands directly unless the user explicitly wants a one-file draft.

When wrappers are relative paths, add them to `user_forward_files` for the corresponding stage:

```json
"user_forward_files": ["wrappers/dp_apptainer.sh"]
```

For Apptainer wrappers, check the wrapper itself, not `machine.json`, owns:

- SIF path
- `apptainer exec`
- `--nv` if GPU is required
- bind paths
- `--pwd "$PWD"`
- MPI executable path, if needed

## MPI Rules

Always state MPI assumptions in comments around the generated file or in the validation summary, not inside arbitrary unknown JSON keys.

- If container `lmp` is MPICH-built, prefer container `mpiexec`/`mpirun` or a host MPICH-compatible launcher.
- Do not mix host OpenMPI launcher with MPICH-built container binaries unless compatibility is proven.
- For VASP host builds, preserve the host MPI launcher path, for example `/usr/bin/mpirun`.
- For multi-node jobs, require explicit confirmation that host MPI, container MPI, scheduler, PMIx/PMI, and network libraries are compatible.

## Bundled Examples

Load or copy these files only when needed:

- `assets/examples/local-shell-cpu-deepmd-lammps-cp2k.machine.json`: local Shell CPU DeePMD/LAMMPS from SIF plus CP2K wrapper.
- `assets/examples/slurm-gpu-deepmd-lammps-host-vasp.machine.json`: Slurm GPU DeePMD/LAMMPS from SIF plus host VASP wrapper.
- `assets/examples/sshcontext-cpu-deepmd-lammps-cp2k.machine.json`: SSHContext remote Shell execution.
- `assets/wrappers/dp_apptainer_cpu.sh`: CPU DeePMD-kit `dp` wrapper template.
- `assets/wrappers/lmp_apptainer_cpu.sh`: CPU LAMMPS wrapper template using the DeePMD-kit SIF.
- `assets/wrappers/cp2k_apptainer_cpu.sh`: CPU CP2K wrapper template.
- `assets/wrappers/dp_apptainer_gpu.sh`: GPU DeePMD-kit `dp` wrapper template using `--nv`.
- `assets/wrappers/lmp_apptainer_gpu.sh`: GPU LAMMPS wrapper template using `--nv`.
- `assets/wrappers/vasp_host.sh`: host VASP wrapper template.
- `assets/bundles/local-gpu-cp2k/`: ready-to-adapt local Shell bundle for GPU DeePMD/LAMMPS plus local CP2K.
- `assets/fixtures/dsh-soap/`: small redacted fixture files copied from the prior DSH SOAP DP-GEN project.
- `assets/scripts/smoke_validate_local_gpu_cp2k.sh`: manual smoke test that copies the local GPU/CP2K bundle to a temporary workdir and calls `validate_machine_runtime`.

When using bundled wrapper templates, replace SIF paths, bind paths, MPI command, queue names, and output expectations with site-specific values before declaring a run ready.

The smoke script requires a host where `apptainer exec` works. It intentionally does not run full `dpgen run`; it probes machine commands with short `--help`/`-h`/`--version` style checks and writes truncated logs.

## Validation Checklist

Before saying a `machine.json` is ready:

- Any available reference `machine*.json` has been read and adapted instead of ignored.
- It has `train`, `model_devi`, and `fp`.
- Each stage has non-empty `command`, `machine.remote_root`, and resource settings.
- Relative wrapper scripts are listed in `user_forward_files`.
- No plaintext password, token, private key, or secret is present.
- Apptainer/SIF paths are documented in wrapper files or an external note.
- MPI family and GPU assumptions are stated.
- FP output files expected by DP-GEN are listed in `user_backward_files` when needed.
- For SSHContext, remote paths are remote-visible, not just local-visible.
- For Slurm/PBS, queue/resource fields match the target cluster policy.
