#!/usr/bin/env bash
# CNC check (docs/enclosure-v2c.md section 7) of every machined v2c part with handbuilt-cad tools/cnc_check.py:
# setups, inside corners vs the cutters, vertical corners, thin walls (CNC-MACHINING-RULES: 0.762 metal, 1.52 composite),
# and reach from +Z / -Z only (a 3-axis job with one flip: anything unreachable from both is an undercut).
# Usage (WSL): bash cnc_v2c.sh F1      -> <run>/F1/cnc/<PN>_cnc.txt / .json
set -u
V="${1:-F1}"; RUN="${RUN_DIR:-$HOME/scratch/encl-v2c/runs}"; CAD="${CAD_HOME:-$HOME/projects/handbuilt-cad}"
PY="${CAD_PY:-$HOME/.venvs/handbuilt-cad/bin/python}"
D="$RUN/$V/cnc"; mkdir -p "$D"
# standard shop end mills (radius, mm): dia 2 / 3 / 4 / 6 / 10 / 12 (fin channels are 4 wide, so a dia 3-4 cutter does them)
echo '{"tool_radii_mm": [1.0, 1.5, 2.0, 3.0, 5.0, 6.0], "spindle_axis": "z", "max_listed": 15}' > "$D/spec.json"
for pn in "CPDM-ENC-101-$V:0.762" CPDM-ENC-104:0.762 CPDM-ENC-105:0.762 CPDM-ENC-106:0.762 CPDM-ENC-107:0.762 CPDM-ENC-108:0.762 CPDM-ENC-109:1.52; do
  p="${pn%%:*}"; w="${pn##*:}"
  cp "$RUN/$V/xref/parts/$p.stp" "$D/$p.step"
  "$PY" "$CAD/tools/cnc_check.py" "$D/$p.step" --spec "$D/spec.json" --min-wall "$w" --reach "+Z,-Z" > "$D/$p.log" 2>&1
  echo "$p rc=$?"; grep -iE "setup|corner|wall|reach|unreach|flag" "$D/${p}_cnc.txt" 2>/dev/null | head -12
done
