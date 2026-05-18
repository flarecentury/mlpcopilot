# Local GPU DeePMD/LAMMPS + Local CP2K Bundle

This bundle is DP-GEN-native. Copy `machine.json` to the DP-GEN workdir as `machine.json`, and copy `wrappers/` beside it.

Expected SIF paths are local to the target machine. Set `MLPCOPILOT_SIF_ROOT`,
`DP_SIF`, or `CP2K_SIF` before running if you do not use `./sifs`:

- `$MLPCOPILOT_SIF_ROOT/dp/deepmd-kit_3.1.3_cuda.sif`
- `$MLPCOPILOT_SIF_ROOT/dp/deepmd-kit_3.1.3_cpu.sif`
- `$MLPCOPILOT_SIF_ROOT/cp2k/cp2k_v20261.sif`

Use `machine.json` for GPU DeePMD/LAMMPS + CPU CP2K.

Use `machine.current-cpu-dp-cp2k.json` only when testing with the CPU DeePMD-kit SIF.

Before running:

```bash
mkdir -p remote/train remote/model_devi remote/fp
```

Confirm binary names on the target machine:

```bash
apptainer exec --nv --no-home "$MLPCOPILOT_SIF_ROOT/dp/deepmd-kit_3.1.3_cuda.sif" sh -lc 'command -v dp; command -v lmp'
apptainer exec --no-home "$MLPCOPILOT_SIF_ROOT/cp2k/cp2k_v20261.sif" sh -lc 'command -v cp2k.psmp || command -v cp2k.popt || command -v cp2k.ssmp'
```

If CP2K uses another binary name:

```bash
export CP2K_BIN=cp2k.popt
```
