"""Order-field PCB stage for board A, board B and the input board (KiCad 9 python). Run last in the board build.

usage: python pcb_bom_fields.py <board.kicad_pcb> <netlist.net>

Every footprint whose symbol carries an MPN follows the schematic: Value, DNP and the fields Manufacturer, MPN, LCSC,
Digi-Key_PN, Alternates (board_fix_pcb.sync_fields; the schematic side is tools/sch_bom_fields.py). Nothing else is
touched: no footprint, pad, track, via or zone change, no refill. Safe to re-run.
"""
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_fix_pcb as F  # noqa: E402
from sch_bom_fields import FIELDS  # noqa: E402

PCB, NET = sys.argv[1], sys.argv[2]
comps = F.read_netlist(NET)
want = {r: c for r, c in comps.items() if c["fields"].get("MPN")}
b = pcbnew.LoadBoard(PCB)
log = F.sync_fields(b, want, FIELDS)
for line in log:
    print("  bom:", line)
if log:
    b.Save(PCB)
print("BOM-field PCB stage:", f"saved, {len(log)} changes on {len(want)} parts" if log else "nothing to change")
