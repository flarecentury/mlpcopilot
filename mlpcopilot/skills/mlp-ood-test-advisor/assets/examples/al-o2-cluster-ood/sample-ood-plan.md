# Sample OOD Plan

## Decision Question

Can the current Al/O checkpoint support finite `Al_n + mO2` cluster AIMD
analysis at `700 K` and `1200 K`, given that the dominant training domain is
periodic bulk and surface data?

## Available Evidence

- Periodic bulk and surface training provenance is available.
- A candidate checkpoint exists.
- CP2K finite-cluster AIMD template is available.
- Example setup and postprocessing scripts are available.

## Recommended OOD Slices

- Periodic-to-finite boundary-condition shift.
- Low-coordination edge and vertex environments.
- Larger cluster-family extrapolation.
- High-temperature AIMD windows.
- Reactive `O2` adsorbate dynamics.

## Minimal Validation Slice Under Tight Budget

- Two cluster sizes, one smaller and one larger.
- One adsorbate loading with `O2`.
- Two temperatures: `700 K` and `1200 K`.
- Force RMSE and relative energy fluctuation RMSE from reference trajectories.

## Missing Evidence And Risk

- Missing explicit acceptance thresholds blocks promotion decisions.
- Missing additional stoichiometry or longer trajectories leaves residual risk.
- Missing targeted inspection of worst frames can hide reactive failure modes.

## Tool And Artifact Plan

- Generate AIMD tasks from the example setup script.
- Run CP2K trajectories with the no-PBC template.
- Postprocess DFT vs MLP forces and energy fluctuations.
- Save metrics, plots, and a written OOD summary.

## Approval Gates

- Approve expensive CP2K runs before launch.
- Approve any new DFT labeling before extending the benchmark.
- Approve checkpoint promotion only after written evidence review.
