#!/usr/bin/env bash
# build + every check for the given variants (default F1); logs in ~/scratch/encl-v2c/logs
# usage: wsl -e bash .../enclosure/v2c/src/build_check_all.sh [F1] [F2]
# before: board STEPs (export_boards.ps1) and vendor STEPs (vendor/README.md) in <repo root>/.claude/cache/enclosure
set -u
HERE="${HERE:-$(cd "$(dirname "$0")" && pwd)}"   # set HERE when running a CR-stripped copy
VARS="${*:-F1}"
L="${SCR:-$HOME/scratch/encl-v2c}/logs"
for V in $VARS; do
  bash "$HERE/run.sh" build_v2c.py "$V" > /dev/null || { echo "build $V failed"; continue; }
  NPROC="${NPROC:-12}" bash "$HERE/run.sh" clearance_v2c.py "$V" > /dev/null
  bash "$HERE/run.sh" show_check.py "$V" > /dev/null
  bash "$HERE/run.sh" lugcheck_v2c.py "$V" > /dev/null
  bash "$HERE/run.sh" bomcheck_v2c.py "$V" > /dev/null
  bash "$HERE/run.sh" mass_v2c.py "$V" > /dev/null
  tr -d '\r' < "$HERE/cnc_v2c.sh" > /tmp/cnc_v2c.sh && bash /tmp/cnc_v2c.sh "$V" > "$L/cnc_$V.log" 2>&1
  echo "== $V"; grep -a '^done' "$L/build_v2c_$V.log"
  grep -v ' 0.0 mm3' "$L/show_check_$V.log" | head -60
  grep -E 'head rule|lug_' "$L/lugcheck_v2c_$V.log"; tail -3 "$L/bomcheck_v2c_$V.log"; grep 'rc=' "$L/cnc_$V.log"
done
echo ALLDONE
