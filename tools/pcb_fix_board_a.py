"""Board A PCB, board-fix stage (KiCad 9 python). Run last in tools/build_board_a.ps1.

usage: python pcb_fix_board_a.py <board.kicad_pcb> <netlist.net>

1. Footprints follow the schematic (tools/sch_board_fix.py): values (U3 MCP2562FD-E/SN, U5 MB85RC64TA), DNP (U1, U14:
   one 5 V converter, U15 TSR 1-2450, is fitted), supplier / maker fields (C6c, P9).
2. Enclosure H: the bottom mask window left at the old U9 spot (x -12.9..-8.94, y 11.38..14.02, no chip there) is removed.
3. C7b: CAN terminator = open solder jumper + 120 ohm, placed on the nearest free top-side spot to U3's CANH/CANL pins
   and routed with route_board_a's router (CAN_H -> jumper -> resistor -> CAN_L).
"""
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_fix_pcb as F  # noqa: E402
import netlist_pins  # noqa: E402
import pcb_rework  # noqa: E402
import route_board_a as R  # noqa: E402

PCB, NET = sys.argv[1:3]
mm, tomm = pcbnew.FromMM, pcbnew.ToMM
U9_WINDOW = (-12.903, 11.379, 3.962, 2.642)          # x, y, w, h (mm) of the leftover B.Mask window

comps = F.read_netlist(NET)
padnet = {(r, p): n for r, rows in netlist_pins.parse(NET).items() for p, fn, n in rows}
b = pcbnew.LoadBoard(PCB)

# ---- 2. leftover mask window (removed first: removal needs a save + reload)
gone = []
for z in b.Zones():
    bb = z.GetBoundingBox()
    if z.IsOnLayer(pcbnew.B_Mask) and not z.IsOnLayer(pcbnew.B_Cu) and \
            all(abs(a - c) < 0.01 for a, c in zip((tomm(bb.GetX()), tomm(bb.GetY()), tomm(bb.GetWidth()), tomm(bb.GetHeight())), U9_WINDOW)):
        gone.append(z)
if len(gone) != 1:
    raise SystemExit(f"expected one B.Mask window at the old U9 spot, found {len(gone)}")
b = pcb_rework.remove_and_reload(b, gone, PCB)
print("enclosure H: B.Mask window at the old U9 spot removed")

# ---- 1. fields, values, DNP
for line in F.sync_fields(b, comps):
    print("  sync:", line)

# ---- 3. CAN terminator
new = sorted(r for r in comps if not r.startswith("#") and b.FindFootprintByReference(r) is None)
jp = next(r for r in new if r.startswith("JP"))
rt = next(r for r in new if r.startswith("R"))
if sorted(new) != sorted([jp, rt]):
    raise SystemExit(f"unexpected new parts: {new}")
F.add_part(b, comps[jp], padnet, F.mid(b, "U3", "6", "7"))
F.add_part(b, comps[rt], padnet, F.xy(F.pad(b, jp, "2")))
R.TW = 0.25
R.setup(b, (-37.0, -32.5, 33.8, 61.2), {"F.Cu": 1.0, "In2.Cu": 1.2, "B.Cu": 6.0})
failed = [n for n in ("CAN_H", "/MCU/CAN_TERM", "CAN_L") if not pcb_rework.reconnect(R, b, n)]
if failed:
    raise SystemExit(f"could not route {failed}")
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
b.Save(PCB)
print("board-fix stage saved")
