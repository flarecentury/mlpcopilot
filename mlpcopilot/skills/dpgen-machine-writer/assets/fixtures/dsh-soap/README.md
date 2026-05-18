# DSH SOAP Fixture

Small DP-GEN-style fixture files adapted from a local development run and
sanitized for public examples.

Included:

- `param.json`
- `machine.original.redacted.json`
- `lmp_NVT.in`
- `lmp_tfMC.in`
- `template_d3.inp`

Large data directories and `iter.*` outputs are intentionally not copied. Use the source project path directly when a smoke test needs real data by path.

The original machine file contained remote credentials. This fixture redacts secret-like fields and should be used only as a structure/reference example.
