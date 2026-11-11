#!/bin/bash
# Build the three bench binaries (A unit 1, A unit 2, B) from a branch (default main) into the bench's
# own folders, so it never collides with build_wsl.sh ($S/src, $S/fw).
# Output: ~/renode-pdm/bench/fw/custompdm_{a_unit1,a_unit2,b_unit1}.elf
set -e
S=~/renode-pdm; . $S/env.sh
B=$S/bench
REPO=${REPO:-/mnt/c/projects/active/custom-pdm}
BRANCH=${1:-main}
[ -d $S/ChibiOS/.git ] || { echo "ChibiOS clone missing: run build_wsl.sh once first"; exit 1; }
rm -rf $B/src; mkdir -p $B/src $B/fw
git -C $REPO archive $BRANCH firmware | tar x -C $B/src
git -C $REPO rev-parse --short $BRANCH > $B/fw/built_from.txt
ln -sfn $S/ChibiOS $B/src/firmware/ChibiOS
cd $B/src/firmware
for spec in "custompdm_a 1" "custompdm_a 2" "custompdm_b 1"; do
  set -- $spec; make clean BOARD=$1 UNIT=$2 >/dev/null 2>&1 || true
  if make -j16 BOARD=$1 UNIT=$2 > $B/fw/build_$1_$2.log 2>&1; then
    echo "OK   $1 unit=$2 warnings=$(grep -c 'warning:' $B/fw/build_$1_$2.log)"
  else
    echo "FAIL $1 unit=$2 (see $B/fw/build_$1_$2.log)"; exit 1
  fi
  cp build/*.elf $B/fw/
done
echo "built from $BRANCH @ $(cat $B/fw/built_from.txt)"; ls -la $B/fw/*.elf
