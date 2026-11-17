"""Generate the input board PCB (KiCad 9 python) from the schematic netlist: place, route, pour.

usage: python gen_input_board_pcb.py <out.kicad_pcb> <netlist.xml>

2-layer, 66 x 64 mm. Wires come in on the left (J2, Micro-Fit 2x6), the cable to board A leaves on the right
(J1, JST GH 12). One row per channel in between (pull-up, pull-down, series R, clamp, cap); both 8-way DIP
switches along the bottom. Every net is routed with route_board_a's A* router (pcb_rework.reconnect joins pads
until each net is one piece), then GND is poured on both layers.
"""
import sys, os, math
import xml.etree.ElementTree as ET
import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import route_board_a as R
import pcb_rework as RW

OUT, NET = sys.argv[1], sys.argv[2]
mm, tomm = pcbnew.FromMM, pcbnew.ToMM
FPDIR = os.path.normpath(os.path.join(os.path.dirname(sys.executable), "..", "share", "kicad", "footprints"))
W, H = 66.0, 64.0

# ---- placement: ref -> (x, y, rotation deg)
ROW0, PITCH = 6.0, 4.5
PLACE = {"J2": (10.0, 24.0, 90), "J1": (60.0, 24.0, 90), "SW1": (21.0, 56.5, 90), "SW2": (45.0, 56.5, 90),
         "H1": (4.0, 60.0, 0), "H2": (62.0, 4.0, 0)}
for i in range(1, 9):
    y = ROW0 + (i - 1) * PITCH
    PLACE[f"R{8 + i}"] = (19.0, y, 0)     # pull-up
    PLACE[f"R{16 + i}"] = (25.0, y, 0)    # pull-down
    PLACE[f"R{i}"] = (32.0, y, 0)         # series
    PLACE[f"D{i}"] = (40.0, y, 90)        # clamp
    PLACE[f"C{i}"] = (47.0, y, 0)         # filter
ya = ROW0 + 8 * PITCH
PLACE.update({"R25": (32.0, ya, 0), "R26": (25.0, ya, 0), "D9": (40.0, ya, 90), "C9": (47.0, ya, 0)})

root = ET.parse(NET).getroot()
pinnet = {}
for net in root.find("nets"):
    for node in net.findall("node"):
        pinnet[(node.get("ref"), node.get("pin"))] = net.get("name")
comps = {c.get("ref"): c for c in root.find("components")}
missing = set(comps) - set(PLACE)
if missing:
    raise SystemExit(f"no placement for {sorted(missing)}")

b = pcbnew.NewBoard(OUT)
b.SetCopperLayerCount(2)
ds = b.GetDesignSettings()
ds.SetCopperLayerCount(2)
# same rules as board A (.kicad_pro); NewBoard starts with hole clearance 0, so the zone fill would run into holes
ds.m_MinClearance = mm(0.2)
ds.m_HoleClearance = mm(0.25)
ds.m_HoleToHoleMin = mm(0.25)
ds.m_CopperEdgeClearance = mm(0.2)
ds.m_TrackMinWidth = mm(0.2)

# board outline
def seg(a, c):
    s = pcbnew.PCB_SHAPE(b)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1])))
    s.SetEnd(pcbnew.VECTOR2I(mm(c[0]), mm(c[1])))
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetWidth(mm(0.1))
    b.Add(s)
pts = [(0, 0), (W, 0), (W, H), (0, H)]
for k in range(4):
    seg(pts[k], pts[(k + 1) % 4])

nets = {}
def netinfo(name):
    if name not in nets:
        ni = b.FindNet(name)
        if ni is None:
            ni = pcbnew.NETINFO_ITEM(b, name)
            b.Add(ni)
        nets[name] = ni
    return nets[name]

for ref, c in comps.items():
    lib, name = c.find("footprint").text.split(":")
    fp = pcbnew.FootprintLoad(os.path.join(FPDIR, lib + ".pretty"), name)
    if fp is None:
        raise SystemExit(f"footprint not found: {lib}:{name}")
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    fp.SetReference(ref)
    fp.SetValue(c.find("value").text)
    x, y, rot = PLACE[ref]
    fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    fp.SetOrientationDegrees(rot)
    ts = c.find("tstamps") if c.find("tstamps") is not None else c.find("tstamp")
    fp.SetPath(pcbnew.KIID_PATH(c.find("sheetpath").get("tstamps").rstrip("/") + "/" + ts.text))
    desc = c.find("description").text if c.find("description") is not None else ""
    for fld in fp.GetFields():
        if fld.GetName() == "Datasheet":
            fld.SetText("")
        elif fld.GetName() == "Description":
            fld.SetText(desc or "")
    if ref.startswith("H"):
        fp.Reference().SetVisible(False)                 # mounting holes: no label at the board edge
    if ref == "J2":
        fp.Reference().SetPosition(pcbnew.VECTOR2I(mm(x + 2.0), mm(y + 13.0)))
    b.Add(fp)
    for pad in fp.Pads():
        n = pinnet.get((ref, pad.GetNumber()))
        if n:
            pad.SetNet(netinfo(n))
print("placed", len(comps), "parts")

# ---- placement check: courtyards inside the board (0.5 mm margin) and not overlapping each other
boxes = {}
for fp in b.GetFootprints():
    cy = fp.GetCourtyard(pcbnew.F_CrtYd)
    bb = cy.BBox() if cy.OutlineCount() else fp.GetBoundingBox(False)
    boxes[fp.GetReference()] = (tomm(bb.GetLeft()), tomm(bb.GetTop()), tomm(bb.GetRight()), tomm(bb.GetBottom()))
bad = []
for r, (l, t, rr, bt) in boxes.items():
    if l < 0.5 or t < 0.5 or rr > W - 0.5 or bt > H - 0.5:
        bad.append(f"{r} outside board: x {l:.1f}..{rr:.1f} y {t:.1f}..{bt:.1f}")
refs = sorted(boxes)
for i, a in enumerate(refs):
    for c in refs[i + 1:]:
        A, C = boxes[a], boxes[c]
        if A[0] < C[2] and C[0] < A[2] and A[1] < C[3] and C[1] < A[3]:
            bad.append(f"{a} overlaps {c}")
if bad or "--place-only" in sys.argv:
    for r in refs:
        l, t, rr, bt = boxes[r]
        print(f"  {r:4} x {l:5.1f}..{rr:5.1f}  y {t:5.1f}..{bt:5.1f}")
    print("PLACEMENT PROBLEMS:" if bad else "placement OK", *bad, sep="\n  ")
    b.Save(OUT)
    sys.exit(1 if bad else 0)

# ---- route every net (signals first, then supply, GND last), pads joined until each net is one piece
R.setup(b, (0.3, 0.3, W - 0.3, H - 0.3), {"F.Cu": 1.0, "B.Cu": 1.4}, layers=["F.Cu", "B.Cu"])
all_nets = sorted({n for n in pinnet.values()})
GND = next(n for n in all_nets if n.lstrip("/") == "GND")        # sheet-local label: "/GND"
P33 = next(n for n in all_nets if n.lstrip("/") == "+3V3")
order = [n for n in all_nets if n not in (P33, GND)] + [P33, GND]
failed = []
for n in order:
    if not RW.reconnect(R, b, n, max_rounds=80):
        failed.append(n)
print("routing failed for:", failed)

# ---- drop duplicate vias (two rounds can land a via on the same spot)
seen, dups = set(), []
tht = [q for f in b.GetFootprints() for q in f.Pads() if q.HasHole() and q.GetNetname()]
for v in b.GetTracks():
    if v.GetClass() == "PCB_VIA":
        k = (v.GetNetname(), v.GetPosition().x, v.GetPosition().y)
        on_tht = any(q.GetNetname() == v.GetNetname() and q.HitTest(v.GetPosition()) for q in tht)
        if k in seen or on_tht:                   # duplicate, or redundant inside a through-hole pad of its net
            dups.append(v)
        seen.add(k)
# ---- merge near-duplicate vias: two router rounds can end a layer hop on vias a hair apart (fab hole check 2026-11-17:
# two +3V3 pairs 0.2 / 0.3 mm apart, holes overlapping; KiCad DRC does not flag same-net holes). The second via goes,
# the track ends on it move to the first one (the hop's tracks are collinear, so nothing else moves), and a track that
# then has zero length or doubles another one goes too.
gone = {v.m_Uuid.AsString() for v in dups}
vias = [v for v in b.GetTracks() if v.GetClass() == "PCB_VIA" and v.m_Uuid.AsString() not in gone]
for i, v in enumerate(vias):
    if v.m_Uuid.AsString() in gone:
        continue
    for w in vias[i + 1:]:
        if w.m_Uuid.AsString() in gone or w.GetNetname() != v.GetNetname():
            continue
        gap = math.hypot(tomm(w.GetPosition().x - v.GetPosition().x), tomm(w.GetPosition().y - v.GetPosition().y)) \
            - tomm(v.GetDrillValue()) / 2 - tomm(w.GetDrillValue()) / 2
        if gap >= 0.25:                            # the board's hole-to-hole rule (JLCPCB via to via: 0.2)
            continue
        p, q = v.GetPosition(), w.GetPosition()
        for t in b.GetTracks():
            if t.GetClass() == "PCB_TRACK" and t.GetNetname() == v.GetNetname():
                if (t.GetStart().x, t.GetStart().y) == (q.x, q.y):
                    t.SetStart(pcbnew.VECTOR2I(p.x, p.y))
                if (t.GetEnd().x, t.GetEnd().y) == (q.x, q.y):
                    t.SetEnd(pcbnew.VECTOR2I(p.x, p.y))
        gone.add(w.m_Uuid.AsString())
        dups.append(w)
        print(f"merged {w.GetNetname()} via at ({tomm(q.x):.2f}, {tomm(q.y):.2f}) into ({tomm(p.x):.2f}, {tomm(p.y):.2f})")
segs = {}
for t in b.GetTracks():
    if t.GetClass() != "PCB_TRACK":
        continue
    a, c = (t.GetStart().x, t.GetStart().y), (t.GetEnd().x, t.GetEnd().y)
    k = (t.GetNetname(), t.GetLayer(), t.GetWidth()) + tuple(sorted((a, c)))
    if a == c or k in segs:
        dups.append(t)
    segs[k] = t
if dups:
    print("removing duplicate vias:", len(dups))
    b = RW.remove_and_reload(b, dups, OUT)
    nets.clear()
    ds = b.GetDesignSettings()
    ds.m_MinClearance, ds.m_HoleClearance, ds.m_HoleToHoleMin = mm(0.2), mm(0.25), mm(0.25)
    ds.m_CopperEdgeClearance, ds.m_TrackMinWidth = mm(0.2), mm(0.2)

# ---- GND pour on both layers
for ly in (pcbnew.F_Cu, pcbnew.B_Cu):
    z = pcbnew.ZONE(b)
    z.SetLayer(ly)
    z.SetNet(netinfo(GND))
    z.SetLocalClearance(mm(0.3))
    z.SetMinThickness(mm(0.25))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    ol = z.Outline()
    ol.NewOutline()
    for x, y in ((0.5, 0.5), (W - 0.5, 0.5), (W - 0.5, H - 0.5), (0.5, H - 0.5)):
        ol.Append(mm(x), mm(y))
    b.Add(z)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
b.Save(OUT)
print("saved", OUT)
if failed:
    sys.exit(1)
