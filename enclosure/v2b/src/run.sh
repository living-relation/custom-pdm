#!/usr/bin/env bash
# Run an enclosure-v2b script in WSL (handbuilt-cad venv). Copies this src folder to scratch (CRLF stripped), runs it.
# Usage (WSL): bash run.sh <script.py> [args...]   -> log in ~/scratch/encl-v2b/logs/
set -u
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WT="$(cd "$SRC/../../.." && pwd)"
SCR=~/scratch/encl-v2b
mkdir -p "$SCR/src" "$SCR/logs" "$SCR/runs"
for f in "$SRC"/*.py "$SRC"/*.csv; do tr -d '\r' < "$f" > "$SCR/src/$(basename "$f")"; done
export CAD_PY=~/.venvs/handbuilt-cad/bin/python RUN_DIR="$SCR/runs" WT="$WT"
export PACK="$WT/.claude/tmp/pack/handoff" VENDOR="$WT/.claude/tmp/vendor"
export PYTHONPATH="$SCR/src"
S="$1"; shift
LOG="$SCR/logs/${S%.py}$(printf '_%s' "$@").log"
cd "$SCR/src"
"$CAD_PY" "$SCR/src/$S" "$@" > "$LOG" 2>&1
echo "rc=$?" >> "$LOG"
tail -60 "$LOG"
