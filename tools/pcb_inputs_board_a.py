"""Board A PCB: input expansion connector J6 (JST GH 12-pin, side entry) + its routes. KiCad 9 python.

usage: python pcb_inputs_board_a.py <board.kicad_pcb> <netlist.xml>
Run after pcb_swap_board_a.py and route_board_a.py (U4's spare pads already carry IN_3..IN_10 from the netlist).

1. J6 placed at the left board edge (free 6.9 x 19.8 mm spot), plug opening facing the edge, linked to its
   schematic symbol (path from the netlist) so DRC schematic parity holds.
2. Pad nets from the netlist. R12 set DNP (cuts the unused IS2 buffer off PC2 / PF_IS2).
3. GND pins 11-12: short stub + via into the In1 GND plane.
4. Signals and +3V3 routed by route_board_a's A* router, preferring In2 (no planes there).
"""
import sys, os, math
import xml.etree.ElementTree as ET
import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import route_board_a as R

PCB, NET = sys.argv[1], sys.argv[2]
mm, tomm = pcbnew.FromMM, pcbnew.ToMM
FP_LIB = os.path.join(os.path.dirname(sys.executable), "..", "share", "kicad", "footprints", "Connector_JST.pretty")
FP_NAME = "JST_GH_SM12B-GHS-TB_1x12-1MP_P1.25mm_Horizontal"
REF, POS = "J6", (-32.4, -1.5)
WIN = (-37.5, -14.0, 30.0, 52.0)
SIG = {str(n): f"/MCU/IN_{n + 2}" for n in range(1, 9)}     # sheet-local labels on the MCU sheet

b = pcbnew.LoadBoard(PCB)
if b.FindFootprintByReference(REF):
    raise SystemExit(f"{REF} already on the board")

root = ET.parse(NET).getroot()
pinnet = {}
for net in root.find("nets"):
    for node in net.findall("node"):
        pinnet[(node.get("ref"), node.get("pin"))] = net.get("name")
comp = next(c for c in root.find("components") if c.get("ref") == REF)
sheet_ts = comp.find("sheetpath").get("tstamps")
sym_ts = comp.find("tstamps").text if comp.find("tstamps") is not None else comp.find("tstamp").text


def netinfo(name):
    ni = b.FindNet(name)
    if ni is None:
        ni = pcbnew.NETINFO_ITEM(b, name)
        b.Add(ni)
    return ni


# ---- 1. place J6
fp = pcbnew.FootprintLoad(os.path.normpath(FP_LIB), FP_NAME)
fp.SetReference(REF)
fp.SetValue(comp.find("value").text)
fp.SetPosition(pcbnew.VECTOR2I(mm(POS[0]), mm(POS[1])))
b.Add(fp)
for deg in (270, 90, 0, 180):
    fp.SetOrientationDegrees(deg)
    mp = [tomm(p.GetPosition().x) for p in fp.Pads() if p.GetNumber() == "MP"]
    sg = [tomm(p.GetPosition().x) for p in fp.Pads() if p.GetNumber() == "1"]
    if max(mp) < sg[0] - 2.0:          # mounting tabs / opening on the left (board edge) side
        break
print(f"J6 at {POS} rot {deg}")
fp.SetPath(pcbnew.KIID_PATH(sheet_ts.rstrip("/") + "/" + sym_ts))
fp.SetSheetname(comp.find("sheetpath").get("names").strip("/").split("/")[-1] or "MCU")
fp.SetSheetfile("MCU.kicad_sch")

# ---- 2. nets
for pad in fp.Pads():
    key = (REF, pad.GetNumber())
    if key in pinnet:
        pad.SetNet(netinfo(pinnet[key]))
expect = dict(SIG, **{"9": "PF_IS2", "10": "+3V3", "11": "GND", "12": "GND"})
got = {p.GetNumber(): p.GetNetname() for p in fp.Pads() if p.GetNumber() != "MP"}
if got != expect:
    raise SystemExit(f"J6 nets differ from plan: {got}")
r12 = b.FindFootprintByReference("R12")
r12.SetDNP(True)

# ---- 3. GND stubs + vias (toward the board interior, staggered so they don't crowd)
def padxy(ref, num):
    for p in b.FindFootprintByReference(ref).Pads():
        if p.GetNumber() == num:
            return tomm(p.GetPosition().x), tomm(p.GetPosition().y)
    raise KeyError((ref, num))

inward = 1 if padxy(REF, "1")[0] > POS[0] else -1
for num, dx in (("11", 2.0), ("12", 3.4)):
    px, py = padxy(REF, num)
    vx = px + inward * dx
    t = pcbnew.PCB_TRACK(b)
    t.SetStart(pcbnew.VECTOR2I(mm(px), mm(py)))
    t.SetEnd(pcbnew.VECTOR2I(mm(vx), mm(py)))
    t.SetWidth(mm(0.3))
    t.SetLayer(pcbnew.F_Cu)
    t.SetNet(netinfo("GND"))
    b.Add(t)
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(pcbnew.VECTOR2I(mm(vx), mm(py)))
    v.SetWidth(mm(R.VIA_D))
    v.SetDrill(mm(R.VIA_DRILL))
    v.SetNet(netinfo("GND"))
    b.Add(v)

# ---- 4. routes
R.setup(b, WIN, {"F.Cu": 1.6, "In2.Cu": 1.0, "B.Cu": 2.5})
# IN_3..IN_10 = PC10, PC11, PB4, PB5, PB13, PC13, PB3 (ex-SWO), PD2
U4 = {f"/MCU/IN_{k}": pin for k, pin in zip(range(3, 11), ("51", "52", "56", "57", "34", "2", "55", "54"))}
U4["PF_IS2"] = "10"
for num, net in list(SIG.items()) + [("9", "PF_IS2")]:
    if pinnet.get(("U4", U4[net])) != net:
        raise SystemExit(f"U4.{U4[net]} is {pinnet.get(('U4', U4[net]))}, expected {net}")
# nearest +3V3 F.Cu SMD pad to J6.10
jx, jy = padxy(REF, "10")
p33 = min(((tomm(p.GetPosition().x), tomm(p.GetPosition().y)) for f in b.GetFootprints() if f.GetReference() != REF
           for p in f.Pads() if p.GetNetname() == "+3V3" and p.IsOnLayer(pcbnew.F_Cu)
           and WIN[0] < tomm(p.GetPosition().x) < WIN[2] and WIN[1] < tomm(p.GetPosition().y) < WIN[3]),
          key=lambda q: (q[0] - jx) ** 2 + (q[1] - jy) ** 2)
print("+3V3 target pad at", p33)
# U4 is 0.5 mm pitch and its neighbours' tracks box the spare pads in on F.Cu. Fan out: from each pad run a short
# F.Cu track (straight out past the tip, then straight or 45 deg) to the nearest spot where a via fits, drop a via,
# and route from there on the inner/bottom layers. Each fan-out becomes an obstacle for the next.
u4 = b.FindFootprintByReference("U4")
ucx, ucy = tomm(u4.GetPosition().x), tomm(u4.GetPosition().y)
CL_EXACT = mm(R.CL + 0.01)          # exact geometry: board rule 0.2 mm + 0.01 mm margin
COPPER = [pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]    # In1 is the GND plane (a zone; it refills)


def obstacles(net, cx, cy, r=8.0):
    """Foreign copper (tracks, vias, pads) near (cx, cy): [(item, has_hole_center_radius or None)]."""
    out = []
    for it in list(b.GetTracks()) + [p for f in b.GetFootprints() for p in f.Pads()]:
        if it.GetNetname() == net and net:
            continue
        bb = it.GetBoundingBox()
        if tomm(bb.GetLeft()) > cx + r or tomm(bb.GetRight()) < cx - r or tomm(bb.GetTop()) > cy + r or tomm(bb.GetBottom()) < cy - r:
            continue
        hole = None
        if it.GetClass() == "PCB_VIA":
            hole = (it.GetPosition(), it.GetDrillValue() / 2)
        elif it.GetClass() == "PAD" and it.HasHole():
            hole = (it.GetPosition(), max(it.GetDrillSize().x, it.GetDrillSize().y) / 2)
        out.append((it, hole))
    return out


def clear(obs, shape, layers):
    for it, _ in obs:
        for ly in layers:
            if it.IsOnLayer(ly) and it.GetEffectiveShape(ly).Collide(shape, CL_EXACT):
                return False
    return True


def holes_clear(obs, c, r):
    for _, h in obs:
        if h and math.hypot(h[0].x - c.x, h[0].y - c.y) - h[1] - r < mm(0.25 + 0.01):
            return False
    return True


def V(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


def fanout(net, pad, sides=(0, 1, -1)):
    """sides: 0 = straight out, 1 / -1 = turn 45 deg one way or the other after the straight run."""
    px, py = tomm(pad.GetPosition().x), tomm(pad.GetPosition().y)
    bb = pad.GetBoundingBox()
    if abs(px - ucx) > abs(py - ucy):
        out, tip = (1 if px > ucx else -1, 0), tomm(bb.GetWidth()) / 2
    else:
        out, tip = (0, 1 if py > ucy else -1), tomm(bb.GetHeight()) / 2
    side = (out[1], out[0])
    obs = obstacles(net, px, py)
    tw = mm(R.TW)
    best = None
    for k1 in range(2, 31):                                   # straight run 0.2 .. 3.0 mm beyond the tip
        s1 = k1 / 10
        a = (px + out[0] * (tip + s1), py + out[1] * (tip + s1))
        if not clear(obs, pcbnew.SHAPE_SEGMENT(V(px, py), V(*a), tw), [pcbnew.F_Cu]):
            break
        for sgn in sides:
            d2 = (out[0] + sgn * side[0], out[1] + sgn * side[1])
            n2 = math.hypot(*d2)
            d2 = (d2[0] / n2, d2[1] / n2)
            for k2 in ([0] if sgn == 0 else []) + list(range(3, 31)):
                s2 = k2 / 10
                v = (a[0] + d2[0] * s2, a[1] + d2[1] * s2)
                if s2 and not clear(obs, pcbnew.SHAPE_SEGMENT(V(*a), V(*v), tw), [pcbnew.F_Cu]):
                    break
                circ = pcbnew.SHAPE_CIRCLE(V(*v), mm(R.VIA_D) // 2)
                if clear(obs, circ, COPPER) and holes_clear(obs, V(*v), mm(R.VIA_DRILL) // 2):
                    if best is None or s1 + s2 < best[0]:
                        best = (s1 + s2, a, v)
                    break
        if best and best[0] <= s1:
            break
    if best is None:
        return None
    _, a, vg = best
    for p0, p1 in (((px, py), a), (a, vg)):
        if math.hypot(p1[0] - p0[0], p1[1] - p0[1]) < 1e-6:
            continue
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(V(*p0))
        t.SetEnd(V(*p1))
        t.SetWidth(tw)
        t.SetLayer(pcbnew.F_Cu)
        t.SetNet(netinfo(net))
        b.Add(t)
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(V(*vg))
    v.SetWidth(mm(R.VIA_D))
    v.SetDrill(mm(R.VIA_DRILL))
    v.SetNet(netinfo(net))
    b.Add(v)
    R.refresh()
    return vg


# ---- 5. free the spare U4 pins, step by step
# PC10, PC11, PC13 already run out to the old expansion test pads (TP8-TP10, now removed): route from those ends.
# PB3 (ex-SWO) runs out to the Tag-Connect J4: cut the last piece at J4 and route from the cut end.
# The rest fan out; a few slow-signal blockers are ripped up first and reconnected after. Plane nets (GND, +3V3,
# +12V) and the crystal are never ripped.
import pcb_rework as RW
EXISTING = ["/MCU/IN_3", "/MCU/IN_4", "/MCU/IN_8", "/MCU/IN_9"]
STEPS = [
    # "refan": ripped nets whose own U4 pin sits in the row; they get a fan-out via first, then reconnect from it
    {"refan": ["/MCU/CAN_STANDBY"],
     "targets": ["/MCU/IN_6", "/MCU/IN_10", "/MCU/IN_5", "/MCU/IN_7"],          # PB5, PD2, PB4, PB13
     "sides": {"/MCU/IN_6": (-1,), "/MCU/IN_5": (-1, 0), "/MCU/IN_10": (1, 0)},
     "rip": [((-3.5, 40.6, 1.0, 43.8), ["I2C1_SCL", "I2C1_SDA", "/MCU/CAN_STANDBY"]),
             ((9.9, 33.0, 11.4, 36.3), ["PF_DSEL3_4", "PF_IN4"])]},
]
escape = {}
doomed = [f for f in b.GetFootprints() if f.GetReference().startswith("TP")]
print("removing test points:", sorted(f.GetReference() for f in doomed))
# SWO copper -> IN_9; drop the piece that touches the Tag-Connect pad
j4 = b.FindFootprintByReference("J4")
for tr in b.GetTracks():
    if tr.GetNetname() == "/MCU/SWO":
        if any(p.GetEffectiveShape(pcbnew.F_Cu).Collide(tr.GetEffectiveShape(pcbnew.F_Cu), 0) for p in j4.Pads()):
            doomed.append(tr)
        else:
            tr.SetNet(netinfo("/MCU/IN_9"))
ripped_by_step = []
for step in STEPS:
    ripped = set()
    for box, nets in step["rip"]:
        gone = RW.ripup(b, set(nets), box)
        doomed += gone
        names = sorted({x.GetNetname() for x in gone})
        ripped |= set(names)
        print(f"rip {len(gone)} items in {box}: {names}")
    ripped_by_step.append(ripped)
b = RW.remove_and_reload(b, doomed, PCB)
R.setup(b, WIN, {"F.Cu": 1.6, "In2.Cu": 1.0, "B.Cu": 2.5})
u4 = b.FindFootprintByReference("U4")
for net in EXISTING:                      # route from the free end of the existing copper (farthest from U4)
    pad = next(q for q in u4.Pads() if q.GetNumber() == U4[net])
    px, py = tomm(pad.GetPosition().x), tomm(pad.GetPosition().y)
    ends = [(tomm(q.x), tomm(q.y), tr.GetLayerName()) for tr in b.GetTracks()
            if tr.GetNetname() == net and tr.GetClass() == "PCB_TRACK" for q in (tr.GetStart(), tr.GetEnd())]
    if not ends:
        raise SystemExit(f"{net}: no existing copper")
    ex, ey, ly = max(ends, key=lambda q: math.hypot(q[0] - px, q[1] - py))
    escape[net] = (ex, ey, [ly])
    print(f"existing {net}: route from ({ex:.2f}, {ey:.2f}) {ly}")
for step, ripped in zip(STEPS, ripped_by_step):
    stuck = []
    for net in step.get("refan", []):
        pad = next(q for q in u4.Pads() if q.GetNetname() == net)
        vg = fanout(net, pad, step.get("sides", {}).get(net, (0, 1, -1)))
        if vg is None:
            stuck.append(net)
        else:
            print(f"re-fan {net}: U4.{pad.GetNumber()} -> via at ({vg[0]:.2f}, {vg[1]:.2f})")
    for net in step["targets"]:
        pad = next(q for q in u4.Pads() if q.GetNumber() == U4[net])
        vg = fanout(net, pad, step.get("sides", {}).get(net, (0, 1, -1)))
        if vg is None:
            stuck.append(net)
        else:
            escape[net] = (vg[0], vg[1], ["In2.Cu", "B.Cu"])
            print(f"fan-out {net}: U4.{U4[net]} -> via at ({vg[0]:.2f}, {vg[1]:.2f})")
    if stuck:
        raise SystemExit(f"no fan-out spot for {stuck}")
    for net in sorted(ripped):
        if not RW.reconnect(R, b, net):
            raise SystemExit(f"could not reconnect ripped net {net}")
        print(f"reconnected {net}")
if "--fanout-only" in sys.argv:
    b.Save(PCB)
    raise SystemExit("fan-out stage only: saved, routes to J6 not done")
num_of = {net: num for num, net in SIG.items()}
jobs = [(net, padxy(REF, num_of[net]) + (["F.Cu"],), (ex, ey, lys)) for net, (ex, ey, lys) in escape.items()]
jobs.append(("PF_IS2", padxy(REF, "9") + (["F.Cu"],), padxy("R12", "1") + (["F.Cu"],)))   # R12 is DNP
jobs.append(("+3V3", padxy(REF, "10") + (["F.Cu"],), p33 + (["F.Cu"],)))
if not R.run_jobs(jobs):
    sys.exit(1)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
b.Save(PCB)
print("saved")
