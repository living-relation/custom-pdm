"""Board B PCB edit (dingoPDM-Max base), stage 1: parts, outline, zones. Run with the KiCad 9 python.

    python.exe tools/pcb_board_b.py <board.kicad_pcb> <netlist.net> <board-a-baseline.kicad_pcb> <board-b-refs.json>

What it does
  * removes the Deutsch DT header J4, every test point and the DRT logo; a test point that joined two layers gets a via
  * renames copper to follow the new schematic (pad nets come from the netlist; tracks follow their pads)
  * T1-T4 (REDCUBE M4) on the four existing output pours; J6 (Micro-Fit 2x2) where J4's CAN / input pins were
  * widens the board 39 mm to the right (72.4 -> 111.4 mm); the bottom layer under the new channels is +12 V (heat)
    and a 7.5 mm strip next to the old edge is kept for the input connector J7 and the sense buffer U22
  * four 15 A channels in that column: placement AND copper copied from dingoPDM v7.5's BTS700x-1EPP channel (U8 block of
    the board A baseline, MIT), turned so the output faces the right edge, with a terminal T5-T8 and an output pour each
Stage 2 (the remaining parts and routing the new signals) is tools/route_board_b.py.

KiCad 9 python traps met here: BOARD.Remove() corrupts item lists (use pcb_rework.remove_and_reload); a NETINFO_ITEM
made in python must get thisown=False; loading a second board switches the project and the first board then crashes on
Save (so the baseline block is read into plain data before the real board is loaded).
"""
import json
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import netlist_pins  # noqa: E402
from board_b_geom import BH, BW, EXT, SEAM, SRC_BOX, block_centres  # noqa: E402
import pcb_rework  # noqa: E402

PCB, NET, SRC, REFS = sys.argv[1:5]
KFP = os.path.join(os.environ["LOCALAPPDATA"], r"Programs\KiCad\9.0\share\kicad\footprints")
DINGO_LIB = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hardware", "board-a", "libraries", "dingoPDM.pretty"))
mm = pcbnew.FromMM
um = lambda v: round(v / 1e6, 3)
V = lambda x, y: pcbnew.VECTOR2I(mm(x), mm(y))

SRC_C = (16.0, 14.95)                        # its centre
SRC_ZONE = (8.38, 0.05, 22.35, 10.67)        # PF_OUT1 pour on the baseline
SRC_MASK = (9.169, 11.379, 13.131, 14.021)   # bottom solder mask opening under U8 (thermal pad contact)
TERM_FP = ("TerminalBlock_Wuerth", "Wuerth_REDCUBE-THR_WP-THRBU_74650074_THR")
T_OLD = {1: (12.0, 4.75), 2: (-12.0, 4.75), 3: (12.0, -4.75), 4: (-12.0, -4.75)}
J6_AT = (-1.5, -1.5)                         # pad 1; pads land at (+-1.5, +-1.5)
OLD_ENDS = {"CAN_L": ((-2.22, -4.56), "F.Cu"), "CAN_H": ((2.22, -4.56), "F.Cu"),
            "INPUT1": ((2.22, 4.56), "In2.Cu"), "INPUT2": ((-2.22, 4.56), "In2.Cu")}

nl = netlist_pins.parse(NET)
refs = json.load(open(REFS))
chan = refs["channel"]
padnet = {(r, p): n for r, rows in nl.items() for p, fn, n in rows}


def read_block():
    """The baseline channel block as plain data (must run before the real board is loaded, see the module note)."""
    sb = pcbnew.LoadBoard(SRC)
    inbox = lambda p: SRC_BOX[0] <= um(p.x) <= SRC_BOX[2] and SRC_BOX[1] <= um(p.y) <= SRC_BOX[3]
    fps, nets = {}, set()
    for sref in chan:
        f = sb.FindFootprintByReference(sref)
        if f.IsFlipped():
            raise SystemExit(f"{sref} is on the bottom side: not handled")
        pads = [(q.GetNumber(), q.GetNetname(), um(q.GetPosition().x), um(q.GetPosition().y)) for q in f.Pads()]
        nets |= {q[1] for q in pads}
        fps[sref] = dict(lib=str(f.GetFPID().GetLibNickname()), name=str(f.GetFPID().GetLibItemName()), x=um(f.GetPosition().x),
                         y=um(f.GetPosition().y), rot=f.GetOrientationDegrees(), value=f.GetValue(), pads=pads)
    trk = []
    for q in sb.GetTracks():
        if q.GetNetname() not in nets or q.GetNetname() == "PF_OUT1":
            continue
        if q.GetClass() == "PCB_VIA":
            if inbox(q.GetPosition()):
                trk.append(("via", q.GetNetname(), um(q.GetPosition().x), um(q.GetPosition().y), q.GetWidth(pcbnew.F_Cu), q.GetDrill()))
        elif inbox(q.GetStart()) and inbox(q.GetEnd()):
            trk.append(("seg", q.GetNetname(), um(q.GetStart().x), um(q.GetStart().y), um(q.GetEnd().x), um(q.GetEnd().y), q.GetWidth(),
                        sb.GetLayerName(q.GetLayer())))
    return fps, trk, sorted(nets)


SRC_FP, SRC_TRK, SRC_NETS = read_block()
b = pcbnew.LoadBoard(PCB)


def netinfo(name):
    ni = b.FindNet(name)
    if ni is None:
        ni = pcbnew.NETINFO_ITEM(b, name)
        ni.thisown = False              # the board owns it now
        b.Add(ni)
    return ni


def ck(tag):
    if os.environ.get("BOARDB_DEBUG"):
        b.Save(PCB + ".dbg")
        print("save ok after", tag, flush=True)


# ---------------------------------------------------------------- 1. remove J4, test points, logo
gone, vias = [], []
for f in b.GetFootprints():
    r = f.GetReference()
    if r == "J4" or r == "G1" or f.GetFPIDAsString().startswith("TestPoint:"):
        gone.append(f)
        if r.startswith("TP"):
            for p in f.Pads():
                layers = set()
                for t in b.GetTracks():
                    if t.GetClass() == "PCB_TRACK" and t.GetNetCode() == p.GetNetCode() and (p.HitTest(t.GetStart()) or p.HitTest(t.GetEnd())):
                        layers.add(t.GetLayer())
                if len(layers) > 1:
                    vias.append((p.GetPosition().x, p.GetPosition().y, p.GetNetname()))
import math  # noqa: E402
import re  # noqa: E402
# stock stitching vias that would sit in a terminal's 4.3 mm screw hole
holed = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"
         and any(math.hypot(um(t.GetPosition().x) - x, um(t.GetPosition().y) - y) < 2.15 + 0.65 for x, y in T_OLD.values())]
print("vias under terminal screw holes removed:", len(holed))
legend = [d for d in b.GetDrawings() if d.GetClass() == "PCB_TEXT" and re.match(r"^\d+(/\d+)?-", d.GetText())]   # J4 pin legend
print("removed:", sorted(f.GetReference() for f in gone), "| J4 legend texts:", len(legend), "| layer-joining test points -> vias:", [(um(x), um(y), n) for x, y, n in vias])
b = pcb_rework.remove_and_reload(b, gone + legend + holed, PCB)
for x, y, n in vias:
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(pcbnew.VECTOR2I(x, y))
    v.SetWidth(pcbnew.F_Cu, mm(0.8))
    v.SetDrill(mm(0.4))
    v.SetNet(netinfo(n))
    b.Add(v)

# ---------------------------------------------------------------- 2. nets follow the new schematic
rename = {}
for f in b.GetFootprints():
    for p in f.Pads():
        new = padnet.get((f.GetReference(), p.GetNumber()))
        if new is None:
            continue
        old = p.GetNetname()
        if old != new:
            if old and not old.startswith("unconnected-") and rename.setdefault(old, new) != new:
                raise SystemExit(f"net {old} splits into {rename[old]} and {new}")
            p.SetNet(netinfo(new))
for t in list(b.GetTracks()) + list(b.Zones()):
    if t.GetNetname() in rename:
        t.SetNet(netinfo(rename[t.GetNetname()]))
dead = [t for t in b.GetTracks() if t.GetNetname().startswith("unconnected-")]      # the old PC13 test point stub
if dead:
    b = pcb_rework.remove_and_reload(b, dead, PCB)
print("copper renamed:", rename, "| dangling stub items removed:", len(dead))


# ---------------------------------------------------------------- helpers to add parts
def finish(f, ref, value=None):
    f.SetReference(ref)
    if value:
        f.SetValue(value)
    for p in f.Pads():
        n = padnet.get((ref, p.GetNumber()))
        if n:
            p.SetNet(netinfo(n))
        elif p.GetNumber():
            p.SetNetCode(0)
    b.Add(f)
    return f


def load(lib, name, ref, x, y, rot=0, value=None):
    f = pcbnew.FootprintLoad(DINGO_LIB if lib == "dingoPDM" else os.path.join(KFP, lib + ".pretty"), name)
    if f is None:
        raise SystemExit(f"footprint {lib}:{name} not found")
    f.SetFPID(pcbnew.LIB_ID(lib, name))
    f.SetPosition(V(x, y))
    f.SetOrientationDegrees(rot)
    f.Reference().SetTextSize(pcbnew.VECTOR2I(mm(1.02), mm(1.02)))     # board rule: silk text >= 1.016 mm high
    f.Reference().SetTextThickness(mm(0.16))
    return finish(f, ref, value)


# ---------------------------------------------------------------- 3. old area: T1-T4, J6
for n, (x, y) in T_OLD.items():
    load(*TERM_FP, f"T{n}", x, y, 0, "74650074R")
j6 = load("Connector_Molex", "Molex_Micro-Fit_3.0_43045-0412_2x02_P3.00mm_Vertical", "J6", *J6_AT, 0, "CAN + IN1-2 (Micro-Fit 2x2)")
for p in j6.Pads():
    net = p.GetNetname()
    if net in OLD_ENDS:
        (x, y), layer = OLD_ENDS[net]
        near = lambda q: abs(q.x - mm(x)) + abs(q.y - mm(y)) < 2000
        w = max([t.GetWidth() for t in b.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetNetname() == net
                 and (near(t.GetStart()) or near(t.GetEnd()))] or [mm(0.3)])
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(V(x, y)); t.SetEnd(p.GetPosition()); t.SetWidth(w); t.SetLayer(b.GetLayerID(layer)); t.SetNet(netinfo(net))
        b.Add(t)
ck("old-area parts")

# ---------------------------------------------------------------- 4. outline and zones
edge = [d for d in b.GetDrawings() if d.GetLayerName() == "Edge.Cuts"]
if len(edge) != 1 or edge[0].GetShape() != pcbnew.SHAPE_T_RECTANGLE:
    raise SystemExit("expected one rectangular outline")
X_OLD = um(max(edge[0].GetStart().x, edge[0].GetEnd().x))
Y0, Y1 = sorted((um(edge[0].GetStart().y), um(edge[0].GetEnd().y)))
X_NEW = X_OLD + EXT
if edge[0].GetEnd().x > edge[0].GetStart().x:
    edge[0].SetEnd(pcbnew.VECTOR2I(mm(X_NEW), edge[0].GetEnd().y))
else:
    edge[0].SetStart(pcbnew.VECTOR2I(mm(X_NEW), edge[0].GetStart().y))
print(f"outline: right edge {X_OLD} -> {X_NEW}; y {Y0} .. {Y1}")


def set_outline(z, pts):
    o = z.Outline()
    o.RemoveAllContours()
    o.NewOutline()
    for x, y in pts:
        o.Append(mm(x), mm(y))
    z.UnFill()


def add_zone(net, layers, pts, prio, like):
    z = pcbnew.ZONE(b)
    ls = pcbnew.LSET()
    for n in layers:
        ls.AddLayer(b.GetLayerID(n))
    z.SetLayerSet(ls)
    if net:
        z.SetNet(netinfo(net))
    z.SetAssignedPriority(prio)
    z.SetLocalClearance(like.GetLocalClearance() or 0)
    z.SetMinThickness(like.GetMinThickness())
    z.SetPadConnection(like.GetPadConnection())
    z.SetThermalReliefGap(like.GetThermalReliefGap())
    z.SetThermalReliefSpokeWidth(like.GetThermalReliefSpokeWidth())
    z.SetIslandRemovalMode(like.GetIslandRemovalMode())
    set_outline(z, pts)
    b.Add(z)
    return z


z12 = zgnd = zout = zmask = None
for z in b.Zones():
    layers = [b.GetLayerName(l) for l in z.GetLayerSet().Seq()]
    if z.GetNetname() == "+12V" and layers == ["B.Cu"]:
        z12 = z
    elif z.GetNetname() == "GND" and z.GetAssignedPriority() == 0:
        zgnd = z
    elif z.GetNetname() == "PF_OUT1":
        zout = z
    elif layers == ["B.Mask"]:
        zmask = z
o = z12.Outline()
pts = [(um(o.CVertex(i).x), um(o.CVertex(i).y)) for i in range(o.TotalVertices())]
i = max(range(len(pts)), key=lambda k: pts[k][0] + pts[k][1])        # the old right edge, lower corner (44.3, 27.2)
j = max(range(len(pts)), key=lambda k: pts[k][0] - pts[k][1])        # the old right edge, upper corner (44.3, -42.4)
if abs(i - j) != 1:
    raise SystemExit(f"+12V outline not as expected: {pts}")
seam = X_OLD + SEAM - 0.3          # the strip keeps the +3V3 plane below it (J7 and U22 tap it with vias)
new = [(seam, pts[i][1]), (seam, Y1 + 8), (X_NEW + 8, Y1 + 8), (X_NEW + 8, pts[j][1])]
pts[min(i, j):max(i, j) + 1] = new if i < j else new[::-1]
set_outline(z12, pts)
o = zgnd.Outline()
pts = [(um(o.CVertex(k).x), um(o.CVertex(k).y)) for k in range(o.TotalVertices())]
set_outline(zgnd, [((X_NEW + 20) if x > 0 else x, y) for x, y in pts])
ck("zones edited")

# ---------------------------------------------------------------- 5. the four 15 A channel blocks
CX, CY = block_centres(X_OLD, Y0, Y1)
print(f"channel blocks {BW:.1f} x {BH:.1f} mm; centres x {CX:.2f}, y {[round(v, 2) for v in CY]}")


def tf(x, y, k):
    """Baseline point -> board B point: quarter turn (baseline 'up' becomes 'right'), then move to block k."""
    dx, dy = x - SRC_C[0], y - SRC_C[1]
    return CX - dy, CY[k] + dx


# which way does pcbnew turn?  we need the turn that sends (0,-1) to (1,0)
probe = pcbnew.PCB_TRACK(b)
probe.SetStart(pcbnew.VECTOR2I(0, -1000000)); probe.SetEnd(pcbnew.VECTOR2I(0, -1000000))
probe.Rotate(pcbnew.VECTOR2I(0, 0), pcbnew.EDA_ANGLE(90, pcbnew.DEGREES_T))
TURN = 90 if probe.GetStart().x > 0 else -90
print("baseline block: nets", SRC_NETS, "| tracks+vias to copy per channel:", len(SRC_TRK))
for k in range(4):
    nmap = {}
    for sref, lst in chan.items():
        s = SRC_FP[sref]
        f = load(s["lib"], s["name"], lst[k], *tf(s["x"], s["y"], k), s["rot"] + TURN, "BTS7004-1EPP" if sref == "U8" else s["value"])
        if f.GetPadCount() != len(s["pads"]):
            raise SystemExit(f"library footprint {s['lib']}:{s['name']} differs from the baseline board")
        num, _, px, py = s["pads"][0]                # the turn must send each pad where the copied tracks expect it
        tp = [q for q in f.Pads() if q.GetNumber() == num][0]
        w = tf(px, py, k)
        if abs(w[0] - um(tp.GetPosition().x)) > 0.02 or abs(w[1] - um(tp.GetPosition().y)) > 0.02:
            raise SystemExit(f"{lst[k]} pad {num} lands at {um(tp.GetPosition().x)},{um(tp.GetPosition().y)}, expected {w}")
        for num, snet, _, _ in s["pads"]:
            tn = padnet.get((lst[k], num), "")
            if nmap.setdefault(snet, tn) != tn and not snet.startswith("unconnected"):
                raise SystemExit(f"channel {k}: baseline net {snet} maps to {nmap[snet]} and {tn}")
    ck(f"block {k} parts")
    for q in SRC_TRK:
        if q[0] == "via":
            n = pcbnew.PCB_VIA(b)
            n.SetPosition(V(*tf(q[2], q[3], k)))
            n.SetWidth(pcbnew.F_Cu, q[4])
            n.SetDrill(q[5])
        else:
            n = pcbnew.PCB_TRACK(b)
            n.SetStart(V(*tf(q[2], q[3], k)))
            n.SetEnd(V(*tf(q[4], q[5], k)))
            n.SetWidth(q[6])
            n.SetLayer(b.GetLayerID(q[7]))
        n.SetNet(netinfo(nmap[q[1]]))
        b.Add(n)
    ck(f"block {k} tracks")
    out = f"PF_OUT{5 + k}"
    load(*TERM_FP, f"T{5 + k}", X_NEW - 5.15, CY[k] - 3.0, 0, "74650074R")     # off-centre: clears the output diode
    x0, y0 = tf(SRC_ZONE[0], SRC_ZONE[3], k)        # zone corner nearest the switch
    x1, y1 = tf(SRC_ZONE[2], SRC_ZONE[1], k)
    xa, xb = sorted((x0, x1)); ya, yb = sorted((y0, y1))
    add_zone(out, ["F.Cu", "B.Cu", "In1.Cu", "In2.Cu"], [(xa, ya - 0.6), (X_NEW + 2, ya - 0.6), (X_NEW + 2, yb), (xa, yb)], 3, zout)
    m0 = tf(SRC_MASK[0], SRC_MASK[1], k); m1 = tf(SRC_MASK[2], SRC_MASK[3], k)
    xa, xb = sorted((m0[0], m1[0])); ya, yb = sorted((m0[1], m1[1]))
    add_zone("", ["B.Mask"], [(xa, ya), (xb, ya), (xb, yb), (xa, yb)], 0, zmask)
    ck(f"block {k} done")

b.Save(PCB)
b = pcbnew.LoadBoard(PCB)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
b.Save(PCB)
fps = {f.GetReference() for f in b.GetFootprints()}
missing = sorted(r for r in nl if r not in fps and not r.startswith("#"))
print("saved. footprints", len(fps), "| in schematic but not on the board yet:", missing)
