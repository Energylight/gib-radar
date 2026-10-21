#!/usr/bin/env bash
# demo/demo.sh — a scripted tour of gib-radar for the hackathon video.
#
# The point of the recording is not "look, it prints text". It is:
#   1. the raw CLI answer is long and undifferentiated;
#   2. the radar turns it into a short ranked list with reasons;
#   3. the same answer is available to an agent over MCP, with no UI at all.
#
# Usage:  bash demo/demo.sh
set -euo pipefail

cd "$(dirname "$0")/.."
export GIB_RADAR_DB="${GIB_RADAR_DB:-/tmp/gib-radar-demo.db}"
export GIB_RADAR_PROFILE="${GIB_RADAR_PROFILE:-stage}"
export GIB_RADAR_ENV="${GIB_RADAR_ENV:-stage}"
rm -f "$GIB_RADAR_DB"

say() { printf '\n\033[1m── %s\033[0m\n' "$*"; }
run() { printf '\033[2m$ %s\033[0m\n' "$*"; eval "$@"; }

say "1. What the platform returns (raw CLI, first task only)"
run "gibwork --profile \"$GIB_RADAR_PROFILE\" --environment \"$GIB_RADAR_ENV\" --json task available --limit 1 \
     | python3 -c 'import json,sys; d=json.load(sys.stdin)[\"data\"][\"results\"][0]; print(json.dumps({k:d[k] for k in (\"title\",\"tags\",\"deadline\",\"totalSubmissions\",\"maxSubmissions\")}, ensure_ascii=False, indent=2))'"

say "2. Scan: the radar collects and stores"
run "python3 -m gib_radar.cli scan --pages 2 --limit 50"

say "3. Rank: what is actually worth doing"
run "python3 -m gib_radar.cli top --limit 5"

say "4. One task, with the score taken apart"
FIRST_ID=$(python3 -m gib_radar.cli top --limit 1 --json | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')
run "python3 -m gib_radar.cli show \"$FIRST_ID\""

say "5. The same answer to an agent, over MCP"
run "printf '%s\n' \
  '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{}}' \
  '{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"radar_top\",\"arguments\":{\"limit\":2}}}' \
  | python3 -m gib_radar.mcp_server \
  | tail -1 | python3 -c 'import json,sys; r=json.load(sys.stdin); print(r[\"result\"][\"content\"][0][\"text\"][:600])'"

say "6. Tests: the scoring and the store are pure functions"
run "python3 -m pytest -q"
