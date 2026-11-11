#!/bin/bash
# Build the custom firmware from the feat/firmware branch inside the WSL sandbox (LF copy of the branch).
set -e
S=~/renode-pdm; . $S/env.sh
REPO=/mnt/c/projects/active/custom-pdm
rm -rf $S/src; mkdir -p $S/src
git -C $REPO archive feat/firmware firmware | tar x -C $S/src
if [ ! -d $S/ChibiOS/.git ]; then
  mkdir -p $S/ChibiOS; cd $S/ChibiOS; git init -q; git remote add origin https://github.com/corygrant/ChibiOS.git
  git fetch -q --depth 1 origin 879cf757d41ed3f9a6648efb666f244374d7f05a; git checkout -q FETCH_HEAD
fi
echo "ChibiOS: $(git -C $S/ChibiOS rev-parse --short HEAD)"
ln -sfn $S/ChibiOS $S/src/firmware/ChibiOS
cd $S/src/firmware; mkdir -p $S/fw
for spec in "custompdm_a 1" "custompdm_a 2" "custompdm_b 1" "dingopdm_v7 "; do
  set -- $spec; make clean BOARD=$1 UNIT=$2 >/dev/null 2>&1 || true
  make -j16 BOARD=$1 UNIT=$2 > $S/fw/build_$1_$2.log 2>&1 && echo "OK   $1 unit=$2 warnings=$(grep -c 'warning:' $S/fw/build_$1_$2.log) $(grep flash0 $S/fw/build_$1_$2.log)" || echo "FAIL $1 unit=$2"
  cp build/*.elf build/*.bin $S/fw/ 2>/dev/null || true
done
ls -la $S/fw | grep -E "elf|bin"
grep -n "can\|adc\|gpioPort[A-C]:\|i2c1\|timer[0-9]*:\|usart\|rcc\|pwr\|flash\|exti\|nvic\|cpu:" $S/renode/platforms/cpus/stm32f4.repl | head -60
