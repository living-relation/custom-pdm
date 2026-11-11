#!/bin/bash
# User-level sandbox for Renode + ARM toolchain + Robot Framework. Everything stays in ~/renode-pdm.
# No sudo, no PATH or profile changes. Remove with: rm -rf ~/renode-pdm
set -e
S=~/renode-pdm; mkdir -p $S/dl; cd $S
RV=1.17.0
if [ ! -x $S/renode/renode ]; then
  curl -fL --retry 3 -o dl/renode.tar.gz https://github.com/renode/renode/releases/download/v$RV/renode-$RV.linux-portable.tar.gz
  mkdir -p renode && tar xf dl/renode.tar.gz -C renode --strip-components=1
fi
if [ ! -x $S/toolchain/bin/arm-none-eabi-gcc ]; then
  URL=$(curl -s https://api.github.com/repos/xpack-dev-tools/arm-none-eabi-gcc-xpack/releases?per_page=30 | grep -o 'https://[^"]*v14\.[^"]*linux-x64\.tar\.gz"' | head -1 | tr -d '"')
  echo "toolchain url: $URL"
  curl -fL --retry 3 -o dl/toolchain.tar.gz "$URL"
  mkdir -p toolchain && tar xf dl/toolchain.tar.gz -C toolchain --strip-components=1
fi
if [ ! -x $S/venv/bin/python ]; then python3 -m venv venv; fi
venv/bin/python -m pip install -q --upgrade pip
echo "== renode tests/requirements.txt"; cat renode/tests/requirements.txt
venv/bin/python -m pip install -q -r renode/tests/requirements.txt 2>&1 | tail -5
cat > env.sh <<'EOT'
# source this to use the sandbox in the current shell only
export PATH=~/renode-pdm/toolchain/bin:~/renode-pdm/renode:~/renode-pdm/venv/bin:$PATH
EOT
echo "== versions"
renode/renode --version 2>&1 | head -2
toolchain/bin/arm-none-eabi-gcc --version | head -1
venv/bin/python --version; venv/bin/python -m pip list 2>/dev/null | grep -i -E "robot|psutil|pyyaml|requests|netifaces|construct"
ls renode/platforms/cpus | grep -i stm32f4; ls renode/platforms/boards | grep -i -E "stm32f4|nucleo_f4" | head
du -sh $S | tail -1
