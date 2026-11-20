"""Board B +12 V feed copper (ADR-2026-11-20-boardb-feed): more copper and stitching on the J1 -> drivers path.

usage (KiCad 9 python; last PCB stage of tools/build_board_b.ps1, after tools/pcb_hole_keepout.py):
    python tools/pcb_feed_board_b.py <board.kicad_pcb>

Why: tools/thermal_board_b.py (real copper, heat sink, gap pad, lid air) puts the bottom-layer +12V pour between J1
and the BTS70012 pair at about 161 C at the 150 A feed limit (laminate limit 130 C): +12V runs on B.Cu only and
In2.Cu is mostly empty. No part, pad, footprint, terminal or hole moves; only copper is added:
  1. In2.Cu: a +12V pour over the whole board (priority 1: the PF_OUT pours, priority 2-5, keep their area; every
     In2 track keeps its clearance). It joins +12V at every through-hole and via that is +12V (J1 pins, the EP via
     arrays under U8-U11 / U23-U26, the stitching vias below).
  2. In1.Cu: a +12V pour over the feed corridor IN1_BAND (x -38..35, y 14.5..28, GND channels to the D14 / D16 vias; priority 9, above the In1 GND
     plane). The ADR lists In1 / In2 / top copper; In2 alone leaves the corridor at 138-144 C. The In1 GND plane
     stays one piece (joined east of x 35) and F.Cu keeps its GND pour, so every GND pad keeps its plane.
  3. B.Cu: the +12V pour edge next to the +3V3 bottom pour moves from the diagonal (-17.23, 33.91) - (-10.92, 26.92)
     - (41.74, 27.21) to (-17.23, 33.91) - (-9.20, 33.91) - (-9.20, 29.00) - (21.50, 29.00) - (21.50, 27.21) -
     (41.74, 27.21): the +3V3 pour keeps every +3V3 via of that band ((-7.87, 29.84), (-0.05, 33.99),
     (23.75, 27.81), (38.29, 33.86)) inside it, so +3V3 stays connected (DRC unconnected = 0 is checked here).
  4. Stitching vias (0.8 / 0.4 mm, the board's +12V via size, JLCPCB standard) on a 2.5 mm grid in the feed corridor (REGIONS)
     (B.Cu +12V and In2 +12V both present), only where a via keeps the board clearance (0.254 mm, the pours') from
     every other-net track, pad, via and hole on every layer, >= 0.6 mm from any other drill, outside every footprint
     courtyard (F and B), outside the hole keep-out rule areas and >= 1 mm from the board edge.
Pours are refilled. Idempotent: zones named 'feed-in2' / 'feed-in1' and vias of the group 'feed-stitch' are removed and redone.
"""
import math
import sys

import pcbnew

mm, tomm = pcbnew.FromMM, pcbnew.ToMM
NAME_IN2 = "feed-in2"
NAME_IN1 = "feed-in1"
IN1_BAND = (-38.0, 14.5, 35.0, 29.0)       # In1.Cu +12V in the feed corridor (x0, y0, x1, y1)
# GND channels kept in In1 through the band: the F.Cu GND pieces of D16 pad 2 and D14 pad 2 hang on the In1 plane
# only through the vias at (-8.5, 23.5) / (9.7, 23.5); each channel (1.6 mm wide) joins its via to the In1 GND plane
# north of the band. (C46's GND piece at x 35.7-39.4 is why the band stops at x 35.)
GND_CHANNELS = [(-8.5, 23.5), (9.7, 23.5)]


def in1_poly():
    x0, y0, x1, y1 = IN1_BAND
    pts = [(x0, y0), (x1, y0), (x1, y1)]
    for cx, cy in sorted(GND_CHANNELS, reverse=True):
        pts += [(cx + 0.8, y1), (cx + 0.8, cy - 0.8), (cx - 0.8, cy - 0.8), (cx - 0.8, y1)]
    return pts + [(x0, y1)]
GROUP = "feed-stitch"
CLR = 0.254          # mm, board pour clearance (the +12V / GND zones)
VIA_D, VIA_DRILL = 0.8, 0.4
PITCH_BAND = 1.5     # mm inside IN1_BAND (In1 is +12V there: only the F.Cu GND pour is perforated)
PITCH = 2.5          # mm: leaves >= 1.7 mm of GND plane (In1 / F.Cu) between two stitching vias' clearance holes
# where the feed current runs (thermal_board_b.py): the corridor J1 -> U8 / U9 and on to the BTS7004 rail, and the
# strip west of the T2 / T4 output pours that carries U10 / U11's share (board B outline -37.87..73.57, -33.3..62)
REGIONS = [(-37.0, 14.0, 45.0, 33.5), (-37.0, -32.0, -23.5, 14.0)]
OLD_EDGE = [(-17.23, 33.91), (-10.92, 26.92), (41.74, 27.21)]
NEW_EDGE = [(-17.23, 33.91), (-9.20, 33.91), (-9.20, 29.00), (21.50, 29.00), (21.50, 27.21), (41.74, 27.21)]


def near(a, b, tol=0.05):
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def b12_zone(b):
    zs = [z for z in b.Zones() if z.GetNetname() == "+12V" and not z.GetIsRuleArea()
          and z.GetLayer() == pcbnew.B_Cu and z.GetZoneName() not in (NAME_IN2, NAME_IN1)]
    if len(zs) != 1:
        raise SystemExit(f"expected one +12V B.Cu pour, found {len(zs)}")
    return zs[0]


def move_edge(z):
    o = z.Outline()
    pts = [(tomm(o.CVertex(i).x), tomm(o.CVertex(i).y)) for i in range(o.TotalVertices())]
    if any(near(p, NEW_EDGE[2]) for p in pts):
        return False                                   # already moved
    i = next((k for k, p in enumerate(pts) if near(p, OLD_EDGE[0])), None)
    if i is None or not near(pts[i + 1], OLD_EDGE[1]) or not near(pts[i + 2], OLD_EDGE[2]):
        raise SystemExit(f"+12V B.Cu outline not as expected: {pts}")
    new = pts[:i] + NEW_EDGE + pts[i + 3:]
    o.RemoveAllContours()
    o.NewOutline()
    for x, y in new:
        o.Append(mm(x), mm(y))
    return True


def add_zone(b, like, name, layer, prio, box=None):
    z = pcbnew.ZONE(b)
    z.SetZoneName(name)
    z.SetLayer(layer)
    z.SetNet(b.FindNet("+12V"))
    z.SetAssignedPriority(prio)
    z.SetLocalClearance(like.GetLocalClearance())
    z.SetMinThickness(like.GetMinThickness())
    z.SetPadConnection(like.GetPadConnection())
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    bb = b.GetBoardEdgesBoundingBox()
    if box is None:
        box = (tomm(bb.GetX()), tomm(bb.GetY()), tomm(bb.GetRight()), tomm(bb.GetBottom()))
    o = z.Outline()
    o.NewOutline()
    pts = box if box and len(box) > 4 else None
    if pts is None:
        x0, y0, x1, y1 = box
        pts = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    for x, y in pts:
        o.Append(mm(x), mm(y))
    b.Add(z)


def blockers(b):
    """(layer -> list of (shape, item)) of every copper item that is not +12V, + all drills, courtyards, keep-outs."""
    cu = [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
    items = {L: [] for L in cu}
    drills = []
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition()
            drills.append((tomm(p.x), tomm(p.y), tomm(t.Cast().GetDrillValue()) / 2))
            if t.GetNetname() == "+12V":
                continue
        if t.GetNetname() == "+12V":
            continue
        for L in cu:
            if t.IsOnLayer(L):
                items[L].append(t.GetEffectiveShape(L))
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetDrillSize().x > 0:
                q = p.GetPosition()
                drills.append((tomm(q.x), tomm(q.y), tomm(max(p.GetDrillSize().x, p.GetDrillSize().y)) / 2))
            if p.GetNetname() == "+12V":
                continue
            for L in cu:
                if p.IsOnLayer(L) or p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    items[L].append(p.GetEffectiveShape(L))
    yards = []
    for fp in b.GetFootprints():
        for side in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
            c = fp.GetCourtyard(side)
            if c.OutlineCount():
                yards.append(c)
    rules = [z for z in b.Zones() if z.GetIsRuleArea()]
    return items, drills, yards, rules


def main(path):
    b = pcbnew.LoadBoard(path)
    zb = b12_zone(b)
    old = [z for z in b.Zones() if z.GetZoneName() in (NAME_IN2, NAME_IN1)]
    oldv = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetParentGroup() is not None
            and t.GetParentGroup().GetName() == GROUP]
    grp = [g for g in b.Groups() if g.GetName() == GROUP]
    if old or oldv or grp:
        for it in old + oldv + grp:
            b.Remove(it)
        b.Save(path)
        b = pcbnew.LoadBoard(path)
        zb = b12_zone(b)
    moved = move_edge(zb)
    # F.Cu GND pour pieces inside IN1_BAND that hung only on the In1 GND plane would be left floating: drop them
    # (the main GND pour has no floating island today: DRC unconnected 0, so only those pieces go)
    for z in b.Zones():
        if z.GetNetname() == "GND" and not z.GetIsRuleArea() and z.GetAssignedPriority() == 0:
            z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    add_zone(b, zb, NAME_IN2, pcbnew.In2_Cu, 1)
    add_zone(b, zb, NAME_IN1, pcbnew.In1_Cu, 9, in1_poly())
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    # candidate sites: B.Cu and In2 +12V copper both present under the whole via pad
    zin2 = next(z for z in b.Zones() if z.GetZoneName() == NAME_IN2)
    fb, fi = zb.GetFilledPolysList(pcbnew.B_Cu), zin2.GetFilledPolysList(pcbnew.In2_Cu)
    items, drills, yards, rules = blockers(b)
    edge = pcbnew.SHAPE_POLY_SET()
    b.GetBoardPolygonOutlines(edge)
    net = b.FindNet("+12V")
    group = pcbnew.PCB_GROUP(b)
    group.SetName(GROUP)
    b.Add(group)
    placed = []
    placed_set = set()
    index = {}                                         # 2 mm bins -> shapes whose box (+ 1 mm) touches the bin
    for L in items:
        for s in items[L]:
            bb = s.BBox()
            for bx in range(int(math.floor((tomm(bb.GetX()) - 1) / 2)), int(math.floor((tomm(bb.GetRight()) + 1) / 2)) + 1):
                for by in range(int(math.floor((tomm(bb.GetY()) - 1) / 2)), int(math.floor((tomm(bb.GetBottom()) + 1) / 2)) + 1):
                    index.setdefault((bx, by), []).append(s)
    r = VIA_D / 2
    sites = []
    for (x0, y0, x1, y1), pt in [(IN1_BAND, PITCH_BAND)] + [(rg, PITCH) for rg in REGIONS]:
        sites += [(x0 + i * pt, y0 + j * pt) for j in range(int((y1 - y0) / pt) + 1)
                  for i in range(int((x1 - x0) / pt) + 1)]
    for x, y in sorted(set((round(x, 3), round(y, 3)) for x, y in sites)):
        if True:
            c = pcbnew.VECTOR2I(mm(x), mm(y))
            ring = pcbnew.SHAPE_CIRCLE(c, mm(r))
            # whole pad inside the filled +12V copper on B.Cu and In2
            if not all(f.Contains(pcbnew.VECTOR2I(mm(x + dx), mm(y + dy))) for f in (fb, fi)
                       for dx, dy in ((0, 0), (r, 0), (-r, 0), (0, r), (0, -r))):
                continue
            if not edge.Contains(c):
                continue
            if min(math.hypot(x - tomm(edge.CVertex(k).x), y - tomm(edge.CVertex(k).y))
                   for k in range(edge.TotalVertices())) < 1.0:
                continue
            if any(math.hypot(x - dx, y - dy) < VIA_DRILL / 2 + dr + 0.6 or
                   (math.hypot(x - dx, y - dy) < PITCH_BAND - 0.01 and (dx, dy) in placed_set) for dx, dy, dr in drills):
                continue
            if any(yd.Contains(c) for yd in yards):
                continue
            if any(z.GetLayerSet().Contains(pcbnew.F_Cu) and z.Outline().Contains(c) for z in rules):
                continue
            if any(s.Collide(ring, mm(CLR)) for s in index.get((int(math.floor(x / 2)), int(math.floor(y / 2))), ())):
                continue
            v = pcbnew.PCB_VIA(b)
            v.SetPosition(c)
            v.SetWidth(mm(VIA_D))
            v.SetDrill(mm(VIA_DRILL))
            v.SetNet(net)
            b.Add(v)
            group.AddItem(v)
            drills.append((x, y, VIA_DRILL / 2))
            placed.append((x, y))
            placed_set.add((x, y))
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    b.Save(path)
    print(f"feed copper: B.Cu +12V edge {'moved' if moved else 'already moved'}; In2 +12V pour; "
          f"{len(placed)} stitching vias ({VIA_D} / {VIA_DRILL} mm, {PITCH} mm grid)")


if __name__ == "__main__":
    main(sys.argv[1])
