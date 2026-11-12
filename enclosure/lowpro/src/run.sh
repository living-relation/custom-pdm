#!/usr/bin/env bash
# Run one low-profile enclosure script in WSL with the handbuilt-cad venv.
# Usage (WSL, repo root):  LP_SRC=$PWD/enclosure/lowpro/src bash <(tr -d "\r" < enclosure/lowpro/src/run.sh) <script.py> [args...]
# Copies this src folder (CR stripped, the checkout is CRLF) to $SCR/work and runs there; log in $SCR/logs/<script>.log.
# Env: SCR (default ~/scratch/encl-lowpro), RUN_DIR (default $SCR/runs/v1), REF_BOARDS (board STEPs, see README),
#      CAD_PY (default ~/.venvs/handbuilt-cad/bin/python), CAD_HOME (default ~/projects/handbuilt-cad).
set -u
SRC="${LP_SRC:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"   # LP_SRC: set it when running a CR-stripped copy of this script
SCR="${SCR:-$HOME/scratch/encl-lowpro}"
mkdir -p "$SCR/work/lowpro" "$SCR/logs"
for f in "$SRC"/*.py; do tr -d '\r' < "$f" > "$SCR/work/lowpro/$(basename "$f")"; done
export CAD_PY="${CAD_PY:-$HOME/.venvs/handbuilt-cad/bin/python}" CAD_HOME="${CAD_HOME:-$HOME/projects/handbuilt-cad}"
export RUN_DIR="${RUN_DIR:-$SCR/runs/v1}" REF_BOARDS="${REF_BOARDS:-$SCR/work/reference/boards}"
S="$1"; shift
LOG="$SCR/logs/${S%.py}.log"
cd "$SCR/work/lowpro"
"$CAD_PY" "$SCR/work/lowpro/$S" "$@" > "$LOG" 2>&1
rc=$?
echo "rc=$rc" >> "$LOG"
tail -40 "$LOG"
exit $rc
