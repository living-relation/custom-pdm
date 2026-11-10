"""Print a board summary: outline box, layers, footprints (ref, lib id, position, side, pad count), zones, track stats.

Run with the KiCad 9 python:  python.exe tools/pcb_info.py <board.kicad_pcb> [ref ...]
With refs given, also lists those footprints' pads (number, net, position, size).
"""
import sys

import pcbnew

b = pcbnew.LoadBoard(sys.argv[1])
mm = lambda v: round(v / 1e6, 3)
r = b.GetBoardEdgesBoundingBox()
print("outline", mm(r.GetX()), mm(r.GetY()), "to", mm(r.GetRight()), mm(r.GetBottom()), "size", mm(r.GetWidth()), "x", mm(r.GetHeight()),
      "copper layers", b.GetCopperLayerCount())
for d in b.GetDrawings():
    if d.GetLayerName() == "Edge.Cuts":
        print("  edge", d.GetClass(), d.ShowShape() if hasattr(d, "ShowShape") else "", mm(d.GetStart().x), mm(d.GetStart().y), mm(d.GetEnd().x), mm(d.GetEnd().y))
print("footprints", len(b.GetFootprints()))
for f in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
    bb = f.GetBoundingBox(False, False)
    print(f"  {f.GetReference():6} {f.GetFPIDAsString():60} at {mm(f.GetPosition().x):8} {mm(f.GetPosition().y):8} rot {f.GetOrientationDegrees():6} "
          f"{'B' if f.IsFlipped() else 'F'} pads {f.GetPadCount():3} box {mm(bb.GetWidth())}x{mm(bb.GetHeight())}")
print("zones")
for z in b.Zones():
    bb = z.GetBoundingBox()
    print(f"  {z.GetNetname():14} {z.GetLayerSet().FmtHex() if False else [b.GetLayerName(l) for l in z.GetLayerSet().Seq()]} box {mm(bb.GetX())},{mm(bb.GetY())} {mm(bb.GetWidth())}x{mm(bb.GetHeight())}"
          f" {'keepout' if z.GetIsRuleArea() else ''}")
tr = [t for t in b.GetTracks()]
print("tracks", sum(1 for t in tr if t.GetClass() == "PCB_TRACK"), "vias", sum(1 for t in tr if t.GetClass() == "PCB_VIA"), "nets", b.GetNetCount())
for ref in sys.argv[2:]:
    f = b.FindFootprintByReference(ref)
    print(ref)
    for p in f.Pads():
        print(f"   pad {p.GetNumber():4} {p.GetNetname():22} {mm(p.GetPosition().x):8} {mm(p.GetPosition().y):8} size {mm(p.GetSize().x)}x{mm(p.GetSize().y)} drill {mm(p.GetDrillSize().x)}")
