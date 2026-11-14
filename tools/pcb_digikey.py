"""Digi-Key PCB stage for board A and board B (KiCad 9 python). Run last in the board build.

usage: python pcb_digikey.py <board.kicad_pcb> <netlist.net>

The footprints of the parts handled by tools/sch_digikey.py (MPN field in its DIGIKEY table) follow the schematic
fields (board_fix_pcb.sync_fields). Nothing else is touched: no footprint, pad, track, via or zone change, no refill.
"""
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_fix_pcb as F  # noqa: E402
from sch_digikey import DIGIKEY  # noqa: E402

PCB, NET = sys.argv[1], sys.argv[2]
comps = F.read_netlist(NET)
want = {r: c for r, c in comps.items() if c["fields"].get("MPN") in DIGIKEY}
for r, c in want.items():
    if c["fields"].get("Digi-Key_PN") != DIGIKEY[c["fields"]["MPN"]]:
        raise SystemExit(f"{r}: schematic Digi-Key_PN not set (run tools/sch_digikey.py and re-export the netlist)")
b = pcbnew.LoadBoard(PCB)
log = F.sync_fields(b, want)
for line in log:
    print("  digikey:", line)
if log:
    b.Save(PCB)
print("Digi-Key PCB stage:", f"saved, {len(log)} changes on {len(want)} parts" if log else "nothing to change")
