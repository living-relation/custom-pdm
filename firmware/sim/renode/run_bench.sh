#!/bin/bash
# One command for the Renode bench (inside WSL): copy the bench files to the sandbox with LF endings, build the
# three firmware binaries if they are missing (or with --build), write bench.resc, run the Robot tests.
# usage: bash run_bench.sh [--build] [extra renode-test / robot arguments]
#   SRC=<this folder>   when the script itself was copied elsewhere (see run_bench.ps1)
#   BRANCH=main         branch to build the firmware from
set -e
S=~/renode-pdm; B=$S/bench; W=$B/work; . $S/env.sh
SRC=${SRC:-$(cd "$(dirname "$0")" && pwd)}
BUILD=0; if [ "$1" = "--build" ]; then BUILD=1; shift; fi
rm -rf $W; mkdir -p $W/models $W/tests $W/sim $B/out
for f in $SRC/*.repl $SRC/*.py $SRC/*.sh $SRC/models/*.cs $SRC/tests/*; do
  sed 's/\r$//' "$f" > "$W/${f#$SRC/}"
done
sed 's/\r$//' $SRC/../pdmsim.py > $W/sim/pdmsim.py
if [ $BUILD = 1 ] || [ ! -f $B/fw/custompdm_b_unit1.elf ]; then
  # a git worktree made by Windows git cannot be read by WSL git: fall back to the main checkout
  REPO=${REPO:-$(git -C $SRC rev-parse --show-toplevel 2>/dev/null || echo /mnt/c/projects/active/custom-pdm)} bash $W/build_bench.sh ${BRANCH:-main}
fi
echo "firmware: built from $(cat $B/fw/built_from.txt 2>/dev/null || echo unknown)"
python3 $W/gen_bench.py $W $B/fw $W/sim $B/out/bench.resc
cd $B/out
renode-test $W/tests/pdm_bench.robot --variable SIMDIR:$W/sim --variable BENCH_RESC:$B/out/bench.resc -r $B/out/results "$@"
