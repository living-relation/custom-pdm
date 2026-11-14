"""Board power-change PCB stage for board A and board B (KiCad 9 python). Run last in the board build.

usage: python pcb_board_power.py <board.kicad_pcb> <netlist.net> A|B

The footprints of the parts changed by tools/sch_board_power.py follow the schematic: value, Digi-Key_PN / LCSC /
Manufacturer / MPN (board_fix_pcb.sync_fields) and, for U2 / U4, Datasheet; and for the power LED and its resistor (A: D3 + R3, B: D5 + R3)
the do-not-fit, exclude-from-BOM and exclude-from-position-files attributes. Nothing else is touched: no footprint,
pad, track, via or zone change, no zone refill. Decisions: DECISIONS.md 2026-11-13 r2a, 2026-11-14 s4a / s6a.
"""
import os
import re
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_fix_pcb as F  # noqa: E402

PCB, NET, BOARD = sys.argv[1], sys.argv[2], sys.argv[3].upper()
OFF = ("R3", {"A": "D3", "B": "D5"}[BOARD])            # power LED resistor + LED (s6a)
REFS = ("U2", "U4") + OFF

comps = F.read_netlist(NET)
for r in OFF:
    if not comps[r]["dnp"]:
        raise SystemExit(f"{r}: not do-not-fit in the schematic (run tools/sch_board_power.py first)")
net_text = open(NET, encoding="utf-8").read().split("(libparts")[0]
sheet = {}                                              # ref -> Datasheet field of the symbol
for blk in re.split(r'\(comp\s+\(ref\s+"', net_text)[1:]:
    m = re.search(r'\(datasheet\s+"([^"]*)"\)', blk)
    sheet[blk[:blk.index('"')]] = m.group(1) if m else ""
b = pcbnew.LoadBoard(PCB)
log = F.sync_fields(b, {r: comps[r] for r in REFS})
for r in ("U2", "U4"):
    f = F._field(b.FindFootprintByReference(r), "Datasheet")
    if sheet[r] and f is not None and f.GetText() != sheet[r]:
        log.append(f"{r} Datasheet {f.GetText()!r} -> {sheet[r]!r}")
        f.SetText(sheet[r])
for r in OFF:
    fp = b.FindFootprintByReference(r)
    if not fp.IsExcludedFromBOM():
        fp.SetExcludedFromBOM(True)
        log.append(f"{r} excluded from BOM")
    if not fp.IsExcludedFromPosFiles():
        fp.SetExcludedFromPosFiles(True)
        log.append(f"{r} excluded from position files")
for line in log:
    print("  power:", line)
if log:
    b.Save(PCB)
print("board power PCB stage:", "saved" if log else "nothing to change")
