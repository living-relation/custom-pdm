"""Board B PCB edit, stage 3 (cosmetic only, no copper, no nets). KiCad 9 python.

    python.exe tools/tidy_board_b.py <board.kicad_pcb> <netlist.net> <baseline.kicad_pcb>

  * fields: every footprint gets the schematic symbol's Digi-Key_PN / LCSC when it lacks them (parts the scripts
    loaded from the KiCad libraries or copied from board A carry none; the schematic copies have them)
  * silkscreen: reference texts of the NEW parts (refs not in the baseline board) that overlap another silk item or an
    exposed pad, or leave the board, are moved to the nearest free spot within 8 mm; if there is none, hidden.
Nothing but text fields is touched: tracks, vias, pads, zones stay as they are.
"""
import math
import re
import sys

import pcbnew

PCB, NET, BASE = sys.argv[1:4]
mm, tomm = pcbnew.FromMM, pcbnew.ToMM
FIELDS = ("Digi-Key_PN", "LCSC")

b = pcbnew.LoadBoard(PCB)

# ---------------------------------------------------------------- fields from the schematic (via the netlist)
sch = {}
text = open(NET, encoding="utf-8").read()
for blk in re.split(r'\(comp\s+\(ref "', text)[1:]:
    ref = blk[:blk.index('"')]
    head = blk.split("(libsource")[0]
    sch[ref] = dict(re.findall(r'\(field\s+\(name "([^"]+)"\)\s+"([^"]*)"\)', head))
added = 0
for fp in b.GetFootprints():
    want = sch.get(fp.GetReference(), {})
    have = {f.GetName() for f in fp.GetFields()}
    for name in FIELDS:
        if name in have or not want.get(name):
            continue
        f = pcbnew.PCB_FIELD(fp, fp.GetNextFieldId(), name)
        f.SetText(want[name])
        f.SetVisible(False)
        f.SetLayer(pcbnew.F_Fab)
        fp.AddField(f)
        added += 1
print("fields added:", added)

# ---------------------------------------------------------------- silkscreen
base_refs = set(re.findall(r'\(property "Reference" "([^"]+)"', open(BASE, encoding="utf-8").read()))
edge = [d for d in b.GetDrawings() if d.GetLayerName() == "Edge.Cuts"]
EB = edge[0].GetBoundingBox()
for d in edge[1:]:
    EB.Merge(d.GetBoundingBox())
EB.Inflate(-mm(0.4))
MARGIN = mm(0.12)


def rect(bb, m=0):
    return pcbnew.SHAPE_RECT(bb.GetX() - m, bb.GetY() - m, bb.GetWidth() + 2 * m, bb.GetHeight() + 2 * m)


def box_at(txt, cx, cy):
    """Bounding box of the text if its centre were at (cx, cy)."""
    old = txt.GetPosition()
    txt.SetPosition(pcbnew.VECTOR2I(cx, cy))
    bb = txt.GetBoundingBox()
    txt.SetPosition(old)
    return bb


def same(a, b):
    return b is not None and a.m_Uuid.AsString() == b.m_Uuid.AsString()


def collect(layer, skip, skipfp=None):
    """Silk items (as bounding boxes) and exposed copper of every other part on the text's side."""
    silk, pads = [], []
    top = layer == pcbnew.F_SilkS
    cu = pcbnew.F_Cu if top else pcbnew.B_Cu
    for fp in b.GetFootprints():
        if fp is skipfp:
            continue
        for it in list(fp.GraphicalItems()):
            if it.GetLayer() == layer and not same(it, skip):
                if it.GetClass() == "PCB_TEXT" and not it.IsVisible():
                    continue
                silk.append(it.GetBoundingBox())
        for fld in (fp.Reference(), fp.Value()):
            if not same(fld, skip) and fld.IsVisible() and fld.GetLayer() == layer:
                silk.append(fld.GetBoundingBox())
        for p in fp.Pads():
            if p.IsOnLayer(cu):
                pads.append(p.GetBoundingBox())
    for d in b.GetDrawings():
        if d.GetLayer() == layer and not same(d, skip):
            silk.append(d.GetBoundingBox())
    return silk, pads


def free(bb, silk, pads):
    if not EB.Contains(bb):
        return False
    for o in silk:
        if bb.Intersects(o):
            return False
    for o in pads:
        if bb.Intersects(o):
            return False
    return True


def grow(bb, m):
    c = pcbnew.BOX2I(bb.GetPosition(), bb.GetSize())
    c.Inflate(m)
    return c


moved, hidden, ok = [], [], 0
for fp in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
    ref = fp.GetReference()
    if ref in base_refs and not re.match(r"T\d$", ref):
        continue
    t = fp.Reference()
    if not t.IsVisible():
        continue
    silk, pads = collect(t.GetLayer(), t)
    silk = [grow(o, MARGIN) for o in silk]
    pads = [grow(o, MARGIN) for o in pads]
    if free(t.GetBoundingBox(), silk, pads):
        ok += 1
        continue
    c0 = t.GetPosition()
    spot = None
    for k in range(1, 33):                                    # radius 0.25 .. 8 mm
        r = k * 0.25
        for a in range(0, 360, 15):
            cx, cy = c0.x + mm(r * math.cos(math.radians(a))), c0.y + mm(r * math.sin(math.radians(a)))
            if free(box_at(t, cx, cy), silk, pads):
                spot = (cx, cy)
                break
        if spot:
            break
    if spot:
        t.SetPosition(pcbnew.VECTOR2I(*spot))
        moved.append(ref)
    else:
        t.SetVisible(False)
        hidden.append(ref)
# the G2 logo (bottom silk) sits on the new terminal T4's pad: shift it to the nearest spot clear of exposed copper
g2 = b.FindFootprintByReference("G2")
if g2 is not None:
    lay = pcbnew.B_SilkS
    own = [d for d in g2.GraphicalItems() if d.GetLayer() == lay]
    if own:
        bb0 = own[0].GetBoundingBox()
        for d in own[1:]:
            bb0.Merge(d.GetBoundingBox())
        pads = collect(lay, None, g2)[1]
        pads += [d.GetBoundingBox() for d in b.GetDrawings() if d.GetLayer() == lay and d.GetClass() == "PCB_TEXT"]   # e.g. 'SUP'
        pads = [grow(o, MARGIN) for o in pads]

        def fits(dx, dy):
            """Exact: the logo's real outlines (not its 19 mm box) against pads and bottom texts."""
            c = pcbnew.BOX2I(bb0.GetPosition() + pcbnew.VECTOR2I(dx, dy), bb0.GetSize())
            if not EB.Contains(c):
                return False
            g2.Move(pcbnew.VECTOR2I(dx, dy))
            try:
                for d in own:
                    sh = d.GetEffectiveShape()
                    dbb = d.GetBoundingBox()
                    for o in pads:
                        if o.Intersects(dbb) and sh.Collide(rect(o), 0):
                            return False
                return True
            finally:
                g2.Move(pcbnew.VECTOR2I(-dx, -dy))
        if fits(0, 0):
            print("G2: fine")
        else:
            done = False
            for k in range(1, 81):                           # radius 0.25 .. 20 mm
                for a in range(0, 360, 15):
                    dx, dy = mm(0.25 * k * math.cos(math.radians(a))), mm(0.25 * k * math.sin(math.radians(a)))
                    if fits(dx, dy):
                        g2.Move(pcbnew.VECTOR2I(dx, dy))
                        print(f"G2 logo moved by ({tomm(dx):.2f}, {tomm(dy):.2f}) mm")
                        done = True
                        break
                if done:
                    break
            if not done:
                print("G2: no clear spot found")
print(f"reference texts: {ok} fine, {len(moved)} moved, {len(hidden)} hidden")
print("moved:", moved)
print("hidden:", hidden)
b.Save(PCB)
print("stage 3 saved")
