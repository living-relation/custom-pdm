#!/usr/bin/env bash
# Start run.sh in the background (WSL), log to ~/scratch/encl-v2c/logs/bg_<name>.log
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; N="$1"; shift
mkdir -p ~/scratch/encl-v2c/logs
nohup bash "$SRC/run.sh" "$@" > ~/scratch/encl-v2c/logs/bg_$N.log 2>&1 &
echo started $!
