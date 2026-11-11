"""Board B PCB edit, stage 2: the parts in the seam strip, then routing of every new signal. KiCad 9 python.

    python.exe tools/route_board_b.py <board.kicad_pcb> <netlist.net>

  * J7 (JST GH 12, top entry), U22 (LM324 sense buffer) with R52-R55 / C46, two more mounting holes
  * MCU (U4, 0.5 mm pitch) fan-outs: short exact-geometry stub + via per new pin, then the grid router joins each net
  * power pins of the new parts: a via to the +3V3 plane (bottom) or the GND plane (inner 1)
Reports every net it could not finish; the build's DRC is the final word.
"""
import math
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import netlist_pins  # noqa: E402
import pcb_rework  # noqa: E402
import route_board_a as R  # noqa: E402
from board_b_geom import EXT, SEAM, block_centres  # noqa: E402

PCB, NET = sys.argv[1:3]
KFP = os.path.join(os.environ["LOCALAPPDATA"], r"Programs\KiCad\9.0\share\kicad\footprints")
mm, tomm = pcbnew.FromMM, pcbnew.ToMM
V = lambda x, y: pcbnew.VECTOR2I(mm(x), mm(y))

b = pcbnew.LoadBoard(PCB)
nl = netlist_pins.parse(NET)
padnet = {(r, p): n for r, rows in nl.items() for p, fn, n in rows}
edge = [d for d in b.GetDrawings() if d.GetLayerName() == "Edge.Cuts"][0]
X_NEW = tomm(max(edge.GetStart().x, edge.GetEnd().x))
Y0, Y1 = sorted((tomm(edge.GetStart().y), tomm(edge.GetEnd().y)))
X_OLD = X_NEW - EXT
CX, CY = block_centres(X_OLD, Y0, Y1)
XS = X_OLD + SEAM / 2                      # strip centre line


def netinfo(name):
    ni = b.FindNet(name)
    if ni is None:
        ni = pcbnew.NETINFO_ITEM(b, name)
        ni.thisown = False
        b.Add(ni)
    return ni


def load(lib, name, ref, x, y, rot=0, value=None, board_only=False):
    f = pcbnew.FootprintLoad(os.path.join(KFP, lib + ".pretty"), name)
    f.SetFPID(pcbnew.LIB_ID(lib, name))
    f.SetPosition(V(x, y))
    f.SetOrientationDegrees(rot)
    f.Reference().SetTextSize(pcbnew.VECTOR2I(mm(1.02), mm(1.02)))     # board rule: silk text >= 1.016 mm high
    f.Reference().SetTextThickness(mm(0.16))
    f.SetReference(ref)
    if value:
        f.SetValue(value)
    if board_only:
        f.SetAttributes(f.GetAttributes() | pcbnew.FP_BOARD_ONLY | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
    for p in f.Pads():
        n = padnet.get((ref, p.GetNumber()))
        if n:
            p.SetNet(netinfo(n))
        else:
            p.SetNetCode(0)
    b.Add(f)
    return f


# ---------------------------------------------------------------- parts in the strip
R0805, C0805 = ("Resistor_SMD", "R_0805_2012Metric"), ("Capacitor_SMD", "C_0805_2012Metric")
load("Connector_JST", "JST_GH_BM12B-GHS-TBT_1x12-1MP_P1.25mm_Vertical", "J7", XS, 44.6, 90, "INPUT BOARD B_IN3-10")
load("Package_SO", "TSSOP-14_4.4x5mm_P0.65mm", "U22", XS, 29.6, 90, "LM324")
load(*C0805, "C46", XS, 24.0, 0, "100nF")
for k, ref in enumerate(("R52", "R53", "R54", "R55")):
    load(*R0805, ref, XS, 12.5 + 2.6 * k, 0, "120R")
for k, ref in ((0, "H5"), (2, "H6")):
    load("MountingHole", "MountingHole_3.2mm_M3_ISO7380_Pad", ref, X_NEW - 4.5, CY[k] + 9.9, 0, "M3", board_only=True)
missing = sorted(r for r in nl if not r.startswith("#") and b.FindFootprintByReference(r) is None)
if missing:
    raise SystemExit(f"still not on the board: {missing}")

# ---------------------------------------------------------------- exact-geometry helpers (KiCad shapes, not the grid)
R.TW = 0.21                                # the board's rule is 0.2032 mm minimum
R.setup(b, (-9.0, Y0 + 0.4, X_OLD + SEAM + 13.0, Y1 - 0.4),      # stops short of the new output pours
        {"F.Cu": 1.2, "In2.Cu": 1.0, "B.Cu": 6.0})   # bottom = power planes: last resort
CL_EXACT = mm(R.CL + 0.01)
COPPER = [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]


def obstacles(net, cx, cy, r=8.0):
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


def add_track(net, p0, p1, w, layer=pcbnew.F_Cu):
    t = pcbnew.PCB_TRACK(b)
    t.SetStart(V(*p0)); t.SetEnd(V(*p1)); t.SetWidth(w); t.SetLayer(layer); t.SetNet(netinfo(net))
    b.Add(t)


def add_via(net, p):
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(V(*p)); v.SetWidth(pcbnew.F_Cu, mm(R.VIA_D)); v.SetDrill(mm(R.VIA_DRILL)); v.SetNet(netinfo(net))
    b.Add(v)


u4 = b.FindFootprintByReference("U4")
ucx, ucy = tomm(u4.GetPosition().x), tomm(u4.GetPosition().y)


def fanout(net, pad, inward=False):
    """Straight F.Cu stub from a U4 pad (away from the chip, or under it), optional 45 degree bend, then a via."""
    px, py = tomm(pad.GetPosition().x), tomm(pad.GetPosition().y)
    bb = pad.GetBoundingBox()
    if abs(px - ucx) > abs(py - ucy):
        out, tip = (1 if px > ucx else -1, 0), tomm(bb.GetWidth()) / 2
    else:
        out, tip = (0, 1 if py > ucy else -1), tomm(bb.GetHeight()) / 2
    if inward:
        out = (-out[0], -out[1])
    side = (out[1], out[0])
    obs = obstacles(net, px, py)
    tw = mm(R.TW)
    best = None
    for k1 in range(2, 41):                                   # straight run 0.2 .. 4.0 mm beyond the tip
        s1 = k1 / 10
        a = (px + out[0] * (tip + s1), py + out[1] * (tip + s1))
        if not clear(obs, pcbnew.SHAPE_SEGMENT(V(px, py), V(*a), tw), [pcbnew.F_Cu]):
            break
        for sgn in (0, 1, -1):
            d2 = (out[0] + sgn * side[0], out[1] + sgn * side[1])
            n2 = math.hypot(*d2)
            d2 = (d2[0] / n2, d2[1] / n2)
            for k2 in ([0] if sgn == 0 else []) + list(range(3, 31)):
                s2 = k2 / 10
                v = (a[0] + d2[0] * s2, a[1] + d2[1] * s2)
                if s2 and not clear(obs, pcbnew.SHAPE_SEGMENT(V(*a), V(*v), tw), [pcbnew.F_Cu]):
                    break
                if clear(obs, pcbnew.SHAPE_CIRCLE(V(*v), mm(R.VIA_D) // 2), COPPER) and holes_clear(obs, V(*v), mm(R.VIA_DRILL) // 2):
                    if best is None or s1 + s2 < best[0]:
                        best = (s1 + s2, a, v)
                    break
        if best and best[0] <= s1:
            break
    if best is None:
        return None
    _, a, vg = best
    for p0, p1 in (((px, py), a), (a, vg)):
        if math.hypot(p1[0] - p0[0], p1[1] - p0[1]) > 1e-6:
            add_track(net, p0, p1, tw)
    add_via(net, vg)
    R.refresh()
    return vg


def via_near(net, x, y, ok=lambda vx, vy: True, max_r=5.0):
    """Short F.Cu stub from (x, y) to the nearest free via spot (not under a part); the via taps a plane."""
    obs = obstacles(net, x, y)
    tw = mm(0.3)
    yards = [f.GetCourtyard(pcbnew.F_CrtYd) for f in b.GetFootprints() if f.GetCourtyard(pcbnew.F_CrtYd).OutlineCount()]
    for k in range(6, int(max_r * 10) + 1):
        r = k / 10
        for a in range(0, 360, 15):
            vx, vy = x + r * math.cos(math.radians(a)), y + r * math.sin(math.radians(a))
            if not ok(vx, vy) or not clear(obs, pcbnew.SHAPE_SEGMENT(V(x, y), V(vx, vy), tw), [pcbnew.F_Cu]):
                continue
            circ = pcbnew.SHAPE_CIRCLE(V(vx, vy), mm(R.VIA_D) // 2)
            if any(cy.Collide(circ, 0) for cy in yards):
                continue
            if clear(obs, circ, COPPER) and holes_clear(obs, V(vx, vy), mm(R.VIA_DRILL) // 2):
                add_track(net, (x, y), (vx, vy), tw)
                add_via(net, (vx, vy))
                R.refresh()
                return vx, vy
    return None


def pad(ref, num):
    return next(p for p in b.FindFootprintByReference(ref).Pads() if p.GetNumber() == num)


failed = []


def tie_to_via(ref, num, w=0.3, max_r=3.0):
    """Real F.Cu track (straight run, then 45 degrees) from a pad to the nearest via of its net.
    For a plane pad that reaches its plane only through a thin neck of the top pour: the router does not see pours,
    so a new via beside the pad could cut it off."""
    p = pad(ref, num)
    net = p.GetNetname()
    x, y = tomm(p.GetPosition().x), tomm(p.GetPosition().y)
    vias = [(tomm(q.GetPosition().x), tomm(q.GetPosition().y)) for q in b.GetTracks() if q.GetClass() == "PCB_VIA" and q.GetNetname() == net]
    vx, vy = min(vias, key=lambda v: math.hypot(v[0] - x, v[1] - y))
    if math.hypot(vx - x, vy - y) > max_r:
        raise SystemExit(f"{ref}.{num}: no {net} via within {max_r} mm")
    kx = vx - abs(vy - y) * (1 if vx > x else -1)
    obs = obstacles(net, x, y)
    for p0, p1 in (((x, y), (kx, y)), ((kx, y), (vx, vy))):
        if not clear(obs, pcbnew.SHAPE_SEGMENT(V(*p0), V(*p1), mm(w)), [pcbnew.F_Cu]):
            raise SystemExit(f"{ref}.{num}: no clear track to the {net} via at ({vx:.2f}, {vy:.2f})")
        add_track(net, p0, p1, mm(w))
    R.refresh()
    print(f"{ref}.{num} {net}: tied to the via at ({vx:.2f}, {vy:.2f})")


# U7.11 (stock LM324 ground pin) hangs on the top pour only; the B_IN5 route from PC13 passes here (B1, 2026-11-10)
tie_to_via("U7", "11")


def join(net):
    try:
        if pcb_rework.reconnect(R, b, net):
            return True
    except ValueError as e:                                   # a point outside the routing window
        print("  ", e)
    failed.append(net)
    return False


# ---------------------------------------------------------------- power pins of the new parts
in_3v3 = lambda vx, vy: vy > 28.2 and X_OLD - 6 < vx < X_OLD + SEAM - 1.0       # the bottom layer is +3V3 there
for ref in ("J7", "U22", "C46"):
    for p in b.FindFootprintByReference(ref).Pads():
        n = p.GetNetname()
        if n not in ("+3V3", "GND") or (ref, n) == ("C46", "+3V3"):
            continue
        x, y = tomm(p.GetPosition().x), tomm(p.GetPosition().y)
        got = via_near(n, x, y, in_3v3 if n == "+3V3" else (lambda vx, vy: True), 9.0 if n == "+3V3" else 5.0)
        print(f"{ref}.{p.GetNumber()} {n}: " + (f"via at ({got[0]:.2f}, {got[1]:.2f})" if got else "NO via spot"))
        if not got:
            failed.append(f"{n} ({ref}.{p.GetNumber()})")
# C46 sits just outside the +3V3 plane area: its +3V3 pad goes to U22's supply pin by track
c46 = next(q for q in b.FindFootprintByReference("C46").Pads() if q.GetNetname() == "+3V3")
u22v = next(q for q in b.FindFootprintByReference("U22").Pads() if q.GetNetname() == "+3V3")
xy = lambda q: (tomm(q.GetPosition().x), tomm(q.GetPosition().y))
if not R.run_jobs([("+3V3", (*xy(c46), ["F.Cu"]), (*xy(u22v), ["F.Cu"]))]):
    failed.append("+3V3 (C46 to U22)")

# ---------------------------------------------------------------- sense buffer nets first (U22's pads get crowded)
done = []
u22 = b.FindFootprintByReference("U22")
u22n = []
for p in u22.Pads():
    n = p.GetNetname()
    if n and n not in ("+3V3", "GND") and n not in u22n:
        u22n.append(n)


def reach(n):                    # longest first: the far channels need the open strip
    ps = [xy(q) for f in b.GetFootprints() for q in f.Pads() if q.GetNetname() == n]
    return -max(math.hypot(a[0] - c[0], a[1] - c[1]) for a in ps for c in ps)


for n in sorted(u22n, key=reach):
    join(n)
    done.append(n)

# ---------------------------------------------------------------- MCU pins: fan out all (tightest first), then route
# Each net is routed FROM ITS FAN-OUT VIA: starting at the 0.5 mm pitch pad itself boxes the grid router in.
# U4.28 (PB2 = BOOT1) is left unconnected: B_IN5 is on U4.2 (PC13), which keeps the stub of its old test point (TP2).
NEW_PINS = ["20", "24", "23", "27", "29", "50", "54", "56", "57", "3", "4", "16", "33", "36", "39", "41"]
STUB_PINS = ["51", "52", "2"]              # PC10, PC11, PC13: routed from the old test point stubs, no new fan-out
fan = {}
for num in NEW_PINS:
    p = pad("U4", num)
    net = p.GetNetname()
    if net != padnet[("U4", num)]:
        raise SystemExit(f"U4.{num} is {net}, expected {padnet[('U4', num)]}")
    vg = fanout(net, p) or fanout(net, p, inward=True)
    print(f"fan-out U4.{num} {net}: " + (f"via at ({vg[0]:.2f}, {vg[1]:.2f})" if vg else "NONE (router tries from the pad)"))
    if vg:
        fan[net] = vg
for num in NEW_PINS + STUB_PINS:
    net = padnet[("U4", num)]
    if net in fan:
        vx, vy = fan[net]
        tgt = min((q for f in b.GetFootprints() if f.GetReference() != "U4" for q in f.Pads() if q.GetNetname() == net),
                  key=lambda q: math.hypot(tomm(q.GetPosition().x) - vx, tomm(q.GetPosition().y) - vy))
        tl = [ly for ly in R.LAYERS if tgt.IsOnLayer(b.GetLayerID(ly))]
        R.run_jobs([(net, (vx, vy, list(R.LAYERS)), (*xy(tgt), tl))])
    elif num == "2":
        # PC13: start at the far end of the old test point stub (the TP2 spot, open board). The stub's near end sits
        # between the fan-outs of pins 3 and 4, where the grid router is boxed in.
        px, py = xy(pad("U4", num))
        ends = [(tomm(e.x), tomm(e.y)) for q in b.GetTracks() if q.GetNetname() == net and q.GetClass() == "PCB_TRACK"
                and q.GetLayer() == pcbnew.F_Cu for e in (q.GetStart(), q.GetEnd())]
        if ends:
            sx, sy = max(ends, key=lambda e: math.hypot(e[0] - px, e[1] - py))
            tgt = min((q for f in b.GetFootprints() if f.GetReference() != "U4" for q in f.Pads() if q.GetNetname() == net),
                      key=lambda q: math.hypot(tomm(q.GetPosition().x) - sx, tomm(q.GetPosition().y) - sy))
            tl = [ly for ly in R.LAYERS if tgt.IsOnLayer(b.GetLayerID(ly))]
            print(f"stub start U4.{num} {net}: ({sx:.2f}, {sy:.2f})")
            R.run_jobs([(net, (sx, sy, ["F.Cu"]), (*xy(tgt), tl))])
    join(net)                                                 # whatever is still separate (third pads, failed first try)
    done.append(net)
print("routed nets:", len(done) - len([f for f in failed if f in done]), "of", len(done), "| FAILED:", failed)

# ---------------------------------------------------------------- tidy: dangling stubs and unused fan-out vias
def prune(nets):
    live = [q for q in b.GetTracks() if q.GetNetname() in nets]
    pads = [q for f in b.GetFootprints() for q in f.Pads() if q.GetNetname() in nets]
    dead, out = set(), []
    changed = True
    while changed:
        changed = False
        for q in live:
            if id(q) in dead:
                continue
            same = [u for u in live if id(u) not in dead and u is not q and u.GetNetCode() == q.GetNetCode()]
            if q.GetClass() == "PCB_VIA":
                c = q.GetPosition()
                lay = {u.GetLayer() for u in same if u.GetClass() == "PCB_TRACK" and u.HitTest(c)}
                on_pad = any(k.GetNetCode() == q.GetNetCode() and k.HitTest(c) for k in pads)
                if len(lay) + (1 if on_pad else 0) < 2:
                    dead.add(id(q)); out.append(q); changed = True
                continue
            for end in (q.GetStart(), q.GetEnd()):
                # held = on a pad, on a via, or exactly on another track's END (touching a track's middle is not a
                # connection for KiCad: DRC calls that stub dangling)
                held = any(k.GetNetCode() == q.GetNetCode() and k.IsOnLayer(q.GetLayer()) and k.HitTest(end) for k in pads) or \
                    any((u.GetClass() == "PCB_VIA" and u.HitTest(end)) or
                        (u.GetClass() != "PCB_VIA" and u.GetLayer() == q.GetLayer() and
                         any(math.hypot(e.x - end.x, e.y - end.y) < mm(0.005) for e in (u.GetStart(), u.GetEnd())))
                        for u in same)
                if not held:
                    dead.add(id(q)); out.append(q); changed = True
                    break
    return out


junk = prune(set(done) | {"I2C1_SCL", "I2C1_SDA"})
print("dangling stubs / unused vias removed:", len(junk))
b = pcb_rework.remove_and_reload(b, junk, PCB)
R.setup(b, (-9.0, Y0 + 0.4, X_OLD + SEAM + 13.0, Y1 - 0.4), {"F.Cu": 1.2, "In2.Cu": 1.0, "B.Cu": 3.0})

# ---------------------------------------------------------------- planes: no floating pour, nothing cut off
# New tracks can fence in a GND pad on the top pour or split the +3V3 plane on the bottom. After each fill, any copper
# group of these nets that is not part of the main one gets a via to its plane, or a routed link to the main group.
WIN = (-9.0, Y0 + 0.4, X_OLD + SEAM + 13.0, Y1 - 0.4)
COST = {"F.Cu": 1.2, "In2.Cu": 1.0, "B.Cu": 6.0}
for z in b.Zones():
    if z.GetNetname() in ("GND", "+3V3"):
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)


def spot(kind, it):
    """(x, y, layers) of a pad / via / track end usable as a router endpoint."""
    if kind == "PAD":
        return [(*xy(it), [ly for ly in R.LAYERS if it.IsOnLayer(b.GetLayerID(ly))])]
    if kind == "PCB_VIA":
        return [(tomm(it.GetPosition().x), tomm(it.GetPosition().y), list(R.LAYERS))]
    if kind == "PCB_TRACK":
        ly = b.GetLayerName(it.GetLayer())
        return [(tomm(q.x), tomm(q.y), [ly]) for q in (it.GetStart(), it.GetEnd())] if ly in R.LAYERS else []
    return []


open_items = []
for rnd in range(4):
    b.Save(PCB)
    b = pcbnew.LoadBoard(PCB)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    R.setup(b, WIN, COST)
    open_items, fixed = [], 0
    for net in ("GND", "+3V3"):
        groups = pcb_rework.net_groups(b, net)
        main = [s for kind, it in groups[0] for s in spot(kind, it) if s[2]]
        for g in groups[1:]:
            pads = [it for kind, it in g if kind == "PAD"]
            if any(q.HasHole() for q in pads):
                continue                    # big through-hole terminals sit in their own pour that touches the main one
            ends = [s for kind, it in g for s in spot(kind, it) if s[2]]
            if not ends:
                continue                    # bare pour: island removal drops it
            name = f"{net} group at ({ends[0][0]:.1f}, {ends[0][1]:.1f})"
            if net == "GND" and pads and via_near("GND", *xy(pads[0])):
                fixed += 1
                continue
            a0, c0 = min(((a0, c0) for a0 in ends for c0 in main), key=lambda pr: math.hypot(pr[0][0] - pr[1][0], pr[0][1] - pr[1][1]))
            if R.run_jobs([(net, a0, c0)]):
                fixed += 1
            else:
                open_items.append(name)
    print(f"plane check round {rnd}: fixed {fixed}, still open {open_items}")
    if not fixed:
        break
# the plane repair adds links and vias too: prune again so no stub it leaves behind dangles (PF_IN8 near 47.4, 42.4)
junk = prune(set(done) | {"I2C1_SCL", "I2C1_SDA"})
print("dangling stubs / unused vias removed after the plane repair:", len(junk))
if junk:
    b = pcb_rework.remove_and_reload(b, junk, PCB)
b.Save(PCB)
print("stage 2 saved | open plane items:", open_items)
