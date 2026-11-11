#!/bin/bash
# Read-only check of what Renode + firmware build need, inside WSL Ubuntu.
echo "== os"; . /etc/os-release; echo "$PRETTY_NAME $(uname -m)"
echo "== sudo without password: $(sudo -n true 2>/dev/null && echo yes || echo no)"
echo "== tools"; for t in python3 pip3 gcc g++ make git curl tar unzip dotnet mono arm-none-eabi-gcc renode pixi docker; do printf "%s: " $t; (command -v $t >/dev/null && ($t --version 2>&1 | head -1)) || echo MISSING; done
echo "== python venv module: $(python3 -c 'import venv, ensurepip; print("ok")' 2>&1 | tail -1)"
echo "== packages"; for p in libicu-dev libgtk2.0-0 gtk-sharp2 policykit-1 uml-utilities screen libc6-dev python3-venv python3-pip python3-dev; do printf "%s: " $p; dpkg-query -W -f='${Version}\n' $p 2>/dev/null || echo not installed; done
echo "== libicu runtime: $(dpkg-query -W -f='${Package} ${Version}\n' 'libicu*' 2>/dev/null | tr '\n' ';')"
echo "== apt candidates"; apt-cache policy gcc-arm-none-eabi libgtk2.0-0 python3-venv 2>/dev/null | grep -E "^[a-z]|Candidate"
echo "== network"; curl -sI -m 15 https://github.com | head -1; curl -s -m 20 https://api.github.com/repos/renode/renode/releases/latest | grep -E '"tag_name"|"name": "renode.*(portable|linux)' | head -8
echo "== home"; ls ~ | head -20; df -h ~ | tail -1
