#!/usr/bin/env bash
# build + clearance + summary for the given variants (default F1 F2); logs in ~/scratch/encl-v2b/logs
# usage: wsl -e bash .../enclosure/v2b/src/build_check_all.sh [F1] [F2]
set -u
HERE="${HERE:-$(cd "$(dirname "$0")" && pwd)}"   # set HERE when running a CR-stripped copy
VARS="${*:-F1 F2}"
for V in $VARS; do
  bash "$HERE/run.sh" build_v2b.py "$V" || { echo "build $V failed"; continue; }
  NPROC="${NPROC:-12}" bash "$HERE/run.sh" clearance_v2b.py "$V" > /dev/null
  bash "$HERE/run.sh" show_check.py "$V" > /dev/null
  echo "== $V"; tail -1 ~/scratch/encl-v2b/logs/build_v2b_"$V".log
  grep -v ' 0.0 mm3' ~/scratch/encl-v2b/logs/show_check_"$V".log | head -60
done
echo ALLDONE
