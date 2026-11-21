#!/usr/bin/env bash
# Run an enclosure-v2c script in WSL (handbuilt-cad venv). Copies this src folder to scratch (CRLF stripped), runs it.
# Usage (WSL): bash run.sh <script.py> [args...]   -> log in ~/scratch/encl-v2c/logs/
# Inputs (git-ignored, outside every worktree so `git worktree remove` keeps them):
#   BOARDS = <repo root>/.claude/cache/enclosure/boards   (export_boards.ps1)
#   VENDOR = <repo root>/.claude/cache/enclosure/vendor   (enclosure/v2c/vendor/README.md)
set -u
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WT="${WT:-$(cd "$SRC/../../.." && pwd)}"
case "$WT" in */.claude/worktrees/*) ROOT="${WT%%/.claude/worktrees/*}";; *) ROOT="$WT";; esac
SCR="${SCR:-$HOME/scratch/encl-v2c}"                  # set SCR for a separate scratch (src copy, logs, runs) per job
mkdir -p "$SCR/src" "$SCR/logs" "$SCR/runs"
for f in "$SRC"/*.py "$SRC"/*.csv; do tr -d '\r' < "$f" > "$SCR/src/$(basename "$f")"; done
export CAD_PY=~/.venvs/handbuilt-cad/bin/python RUN_DIR="${RUN_DIR:-$SCR/runs}" WT="$WT"
export BOARDS="${BOARDS:-$ROOT/.claude/cache/enclosure/boards}" VENDOR="${VENDOR:-$ROOT/.claude/cache/enclosure/vendor}"
export CAD_HOME="${CAD_HOME:-$HOME/projects/handbuilt-cad}" RENDER_DIR="${RENDER_DIR:-$SCR/renders}"
export PYTHONPATH="$SCR/src"
S="$1"; shift
LOG="$SCR/logs/${S%.py}$(printf '_%s' "$@").log"
cd "$SCR/src"
"$CAD_PY" "$SCR/src/$S" "$@" > "$LOG" 2>&1
echo "rc=$?" >> "$LOG"
tail -60 "$LOG"
