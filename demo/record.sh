#!/usr/bin/env bash
# demo/record.sh — run the demo against the live board and capture a transcript.
#
# The transcript is the real stdout/stderr of the commands below, with ANSI
# colour stripped, so the rendered video cannot flatter the tool: whatever
# the radar prints is what the judge sees.
#
# Production reads need a keypair file (the CLI will not read production
# without one). Set GIB_RADAR_KEYPAIR or pass it as the first argument.
set -euo pipefail
cd "$(dirname "$0")/.."

export GIB_RADAR_DB="${GIB_RADAR_DB:-/tmp/gib-radar-demo.db}"
export GIB_RADAR_PROFILE="${GIB_RADAR_PROFILE:-stage}"
export GIB_RADAR_ENV="${GIB_RADAR_ENV:-production}"
export GIB_RADAR_KEYPAIR="${1:-${GIB_RADAR_KEYPAIR:-$HOME/.config/gibwork/stage-id.json}}"
rm -f "$GIB_RADAR_DB"

OUT="demo/transcript.txt"
: > "$OUT"

capture() {
  # run a command, strip ANSI, append to the transcript
  printf '$ %s\n' "$1" >> "$OUT"
  eval "$1" 2>&1 | sed -e 's/\x1b\[[0-9;]*m//g' >> "$OUT" || true
  printf '\n' >> "$OUT"
}

capture "python3 -m gib_radar.cli scan --pages 1 --limit 50"
capture "python3 -m gib_radar.cli top --limit 5"
FIRST_ID=$(python3 -m gib_radar.cli top --limit 1 --json | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')
capture "python3 -m gib_radar.cli show $FIRST_ID"
capture "printf '%s\\n' '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"radar_top\",\"arguments\":{\"limit\":2}}}' | python3 -m gib_radar.mcp_server"
capture "python3 -m pytest -q"

echo "transcript: $OUT ($(wc -l < "$OUT") lines)"
python3 demo/render.py "$OUT"
