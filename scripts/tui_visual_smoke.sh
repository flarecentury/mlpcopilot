#!/usr/bin/env bash
set -euo pipefail

workspace="${MLPCOPILOT_SMOKE_WORKSPACE:-$(mktemp -d /tmp/mlpcopilot-tui-smoke.XXXXXX)}"
config="${MLPCOPILOT_SMOKE_CONFIG:-$workspace/config.json}"

if [[ -n "${MLPCOPILOT_BIN:-}" ]]; then
  read -r -a mlpcopilot_cmd <<< "$MLPCOPILOT_BIN"
elif command -v mlpcopilot >/dev/null 2>&1; then
  mlpcopilot_cmd=(mlpcopilot)
elif command -v uv >/dev/null 2>&1; then
  mlpcopilot_cmd=(uv run mlpcopilot)
else
  echo "Could not find mlpcopilot or uv. Set MLPCOPILOT_BIN." >&2
  exit 1
fi

mkdir -p "$workspace"
cat > "$config" <<JSON
{
  "runtimeProfile": "mlpcopilot",
  "agents": {
    "defaults": {
      "workspace": "$workspace",
      "model": "smoke-model"
    }
  }
}
JSON

echo "MLP Copilot TUI visual smoke"
echo "workspace=$workspace"
echo "config=$config"
echo

for size in 140x36 100x28 80x24 60x18; do
  cols="${size%x*}"
  lines="${size#*x}"
  out="$workspace/tui-${size}.ansi"
  COLUMNS="$cols" LINES="$lines" "${mlpcopilot_cmd[@]}" tui --config "$config" --once > "$out"
  echo "rendered $size -> $out"
done

cat <<EOF

Manual terminal checks:
1. Ordinary terminal: ${mlpcopilot_cmd[*]} tui --config "$config"
2. Narrow terminal: resize to about 80x24, then repeat.
3. Very narrow terminal: resize to about 60x18, then repeat.
4. VS Code terminal: repeat inside VS Code integrated terminal.

Pass criteria:
- no traceback
- no overlapping panels or unreadable input footer
- slash menu, approvals, job picker, and Ctrl-T pager open and close
- !echo smoke runs and returns to the input prompt
EOF
