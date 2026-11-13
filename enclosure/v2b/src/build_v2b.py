"""custom-pdm enclosure v2b - Grok TEST 2 variant b, changed only where DECISIONS.md 2026-11-12 requires.
build123d (handbuilt-cad CAD venv, DansPC WSL). Usage: python build_v2b.py F1|F2
  F1 = Grok's 2 x 30 mm Sunon fans embedded inside the heat-sink envelope (fan bay at the east end, push west)
  F2 = one Noctua NF-A6x15 blowing UP into a machined pocket in the fin field, swept radial fins
Base: Grok's build_test2.py (pack custom-pdm-enclosure-handoff.zip, test2/src), same world frame:
X east, Y north, Z up, Z=0 = heat-sink field, board north edges at Y=0. Units mm.
Changes vs Grok b (all from DECISIONS.md 2026-11-12):
  - front (south) long side moved south so X1/X2 mount HORIZONTALLY on the front wall in drafted round turrets (h2a,
    'deeper housing'); turrets on the top removed; main body top raised so the connector panel nut fits
  - real TE STEP models for X1/X2 and mating plugs, Noctua STEP, Adafruit hub STEP (VENDOR folder, not in git)
  - BATT/GND copper bars inside (e4a/b1b) instead of cable links; custom copper bosses (v3b) instead of brass extensions
  - one sealed USB-C bulkhead + internal hub (y1a) instead of 3 USB slots
  - reinforced feet (hex, webbed), fans embedded (v5)
  - board A without J3 header (wire pads, a1a), board B without J6 Micro-Fit (a2b); wire ribbons to X1/X2
ASSUMED = designer's choice, TBD = not confirmed by a primary source.
"""
import os, sys, json, math
from build123d import *
VAR = sys.argv[1] if len(sys.argv) > 1 else "F1"
PACK = os.environ["PACK"]; VENDOR = os.environ["VENDOR"]
REF = os.path.join(PACK, "test2", "reference", "boards")
OUT = os.path.join(os.environ.get("RUN_DIR", "/tmp/v2b"), VAR)
import shutil
for _d in ("parts", "brep"):                                         # clear stale outputs so the clearance check sees only this build
    shutil.rmtree(os.path.join(OUT, _d), ignore_errors=True); os.makedirs(os.path.join(OUT, _d), exist_ok=True)
from screwtool_twin import shcs, standoff_mf
class _BB:
    def __init__(self, b):
        self.xmin, self.ymin, self.zmin = b.min.X, b.min.Y, b.min.Z
        self.xmax, self.ymax, self.zmax = b.max.X, b.max.Y, b.max.Z
        self.xlen, self.ylen, self.zlen = b.size.X, b.size.Y, b.size.Z
def bbx(s): return _BB(s.bounding_box())
def isect(a, b):
    r = a.intersect(b)
    if isinstance(r, list): r = r[0] if len(r) == 1 else Compound(list(r))
    return r
def one(s):
    so = s.solids()
    return so[0] if len(so) == 1 else Compound(list(so))

# ---------------- driving dimensions ----------------
P = dict(
    gap_boards=2.0, ped_h=3.0, pad_t=1.0, plate_t=8.0,
    fin_h=30.0, fin_t=2.0, fin_pitch=6.0, fin_edge=10.0,      # Grok's straight fins (F1)
    foot_h=10.0, foot_af=24.0, foot_web_t=4.0, foot_web_L=20.0,  # reinforced feet: hex AF24, 2 webs each, 10 below fin tips (was dia 16, 6 below)
    wall=3.0, edge_clear=10.0,
    lid_y0=-130.0,           # front (south) outer face of the skirt: moved south from Grok b (-109.25) so X1/X2 rear bodies + wire bend clear the input deck
    terrace_top=30.0, collar_top=38.23,                       # Grok 32.23; +6 so the M6 boss is 15 tall (stud 6 + lug screw 8 engagement)
    main_top=66.0,           # raised from 55: the front turrets (dia 62, axis Z 33) and the panel nut must fit under the body top
    turret_d=62.0, turret_z=33.0, turret_bore=54.0, turret_len=24.0,
    usb_turret_d=46.0, usb_z=30.0,   # raised so the bulkhead's rear cable runs above the board components (max z 19.2)
    deck_t=3.0, in_boss=4.0, so_m3_len=25.0,
    bar_t=5.0, batt_w=20.0, batt_yc=-63.5, gnd_w=15.0, gnd_yc=-5.0,   # copper bars (C110) 20x5 / 15x5, offset in Y to clear the OUT-bay liner
    boss6_af=13.0, boss4_d=9.5, boss4_flats=8.0, lug_t=2.0,
    bay_floor_top=19.2,      # OUT1-4 bay floor; lowered 0.53 so the ring-lug barrels (OD 6) clear it
    out_lug_t=1.0, out_lug_w=8.0, out_lug_L=17.5, out_barrel_d=6.0, out_barrel_L=8.0, out_wire_d=4.2,   # Phoenix 3240083 M4 ring 10-14 AWG (catalogue dims); 10 AWG GXL OD ~4.2 ASSUMED
    out_seat_lo=19.0, out_seat_hi=25.0,                       # OUT1-4 lug seat tops: west pair (OUT2/OUT4) low tier, east pair (OUT1/OUT3) high tier (Dan d1a 2026-11-13)
    riser_r=4.0, riser_foot=4.0, pocket_d=5.0, ear_t=5.0,     # copper offset risers: foot arm R4 x 4 thick, seat column R4 (= lug ring OD 8); lug pockets 5 deep in the G10 carrier; ears 5 thick
    wireway_y0=-47.2, wireway_y1=-19.3,                      # OUT1-4 wire-way (Dan 2026-11-12): between the BATT and GND collars, open at the west lid edge
    corner_r=14.0, draft_deg=6.0, shoulder_z=10.0, shoulder_in=2.0,
    ribbon_w=28.0, ribbon_t=4.0,                               # flat taped wire ribbons (ASSUMED harness form)
)
Z_BOT = P["ped_h"] + P["pad_t"]; T_PCB = 1.769872; Z_TOP = Z_BOT + T_PCB
X0 = {"B": 0.0}; X0["A1"] = 111.39 + P["gap_boards"]; X0["A2"] = X0["A1"] + 72.39 + P["gap_boards"]
def W(n, xk, yk): return (X0[n] + xk + 37.846, -(yk + 33.274))

stepA_full = import_step(os.path.join(REF, "board-A.step"))
stepB_full = import_step(os.path.join(REF, "board-B.step"))
stepI = import_step(os.path.join(REF, "input-board.step"))
def strip(s, cx0, cy0, rxy, zmin_keep):
    """drop solids centred within rxy of (cx0,cy0) (board-local) that rise above zmin_keep or are pin tails"""
    keep, dropped = [], 0
    for so in s.solids():
        b = bbx(so); cx, cy = (b.xmin + b.xmax) / 2, (b.ymin + b.ymax) / 2
        if abs(cx - cx0) < rxy and abs(cy - cy0) < rxy and (b.zmax > zmin_keep or b.zmin < -0.5) and b.xlen < 70: dropped += 1; continue
        keep.append(so)
    return Compound(keep), dropped
stepA, dA = strip(stepA_full, 0.0, 0.0, 16.0, 6.0)        # J3 DT15-12PA body + pins (a1a: wire pads only)
stepB, dB = strip(stepB_full, -1.5, 1.5, 4.5, 3.0)         # J6 Micro-Fit body + pins (a2b: wire pads only); local y = -yk
parts = {}
def addp(name, shape, color, label, step=True):
    shape = shape if name.startswith(("board", "input-board", "vendor")) else one(shape)
    parts[name] = dict(shape=shape, color=color, label=label, step=step)
def box(x0, x1, y0, y1, z0, z1):
    x0, x1 = sorted((x0, x1)); y0, y1 = sorted((y0, y1)); z0, z1 = sorted((z0, z1))
    return Solid.make_box(x1 - x0, y1 - y0, z1 - z0, Plane(origin=(x0, y0, z0)))
def cyl(d, p0, L, axis=(0, 0, 1)):
    return Solid.make_cylinder(d / 2, L, Plane(origin=p0, z_dir=axis))
def hexp(af, p0, L, axis=(0, 0, 1), rot=30.0):
    return extrude(Plane(origin=p0, z_dir=axis) * Rot(0, 0, rot) * RegularPolygon(af / 2 / math.cos(math.pi / 6), 6), amount=L).solid()
def dblock(x0, x1, y0, y1, z0, z1, r=8, draft=0.0, tf=0.0):
    w, h = x1 - x0, y1 - y0
    sk = Pos((x0 + x1) / 2, (y0 + y1) / 2, z0) * RectangleRounded(w, h, min(r, w / 2 - 0.5, h / 2 - 0.5))
    s = extrude(sk, amount=z1 - z0, taper=draft).solid()
    if tf: s = s.fillet(tf, s.faces().sort_by(Axis.Z)[-1].edges())
    return s
def dround(cx, cy, d, z0, z1, draft=0.0, tf=0.0):
    s = extrude(Pos(cx, cy, z0) * Circle(d / 2), amount=z1 - z0, taper=draft).solid()
    if tf: s = s.fillet(tf, s.faces().sort_by(Axis.Z)[-1].edges())
    return s
def tube(pts, d):
    """round wire/cable as a chain of cylinders + spheres through pts"""
    s = None
    for a, b in zip(pts[:-1], pts[1:]):
        a, b = Vector(*a), Vector(*b); L = (b - a).length
        c = Solid.make_cylinder(d / 2, L, Plane(origin=a, z_dir=(b - a).normalized())).fuse(Solid.make_sphere(d / 2).translate(b))
        s = c if s is None else s.fuse(c)
    return s.fuse(Solid.make_sphere(d / 2).translate(Vector(*pts[0])))
def ribbon(pts, w, t):
    """flat taped wire ribbon (width w horizontal, thickness t) through pts: chain of oriented boxes"""
    s = None
    for a, b in zip(pts[:-1], pts[1:]):
        a, b = Vector(*a), Vector(*b); d = b - a; L = d.length
        side = Vector(0, 0, 1).cross(d.normalized())
        if side.length < 1e-6: side = Vector(1, 0, 0)
        side = side.normalized(); up = d.normalized().cross(side)
        pl = Plane(origin=a - side * (w / 2) - up * (t / 2), x_dir=side, z_dir=d.normalized())
        seg = Solid.make_box(w, t, L + t, Plane(origin=pl.origin, x_dir=side, z_dir=d.normalized())).translate(-d.normalized() * (t / 2))
        s = seg if s is None else s.fuse(seg)
    return s

# ---------------- boards ----------------
for n in ("B", "A1", "A2"):
    ox = X0[n] + 37.846
    addp(f"board-{n}", (stepB if n == "B" else stepA).translate(Vector(ox, -33.274, Z_BOT)), (0.1, 0.45, 0.15),
         "board STEP from Grok pack (KiCad 10.0.7 export of feat/board-fix); " + ("J6 Micro-Fit body removed (a2b, main @ 355ee4a)" if n == "B" else "J3 DT15-12PA removed (a1a, main @ 355ee4a)"), step=False)
IN_X = {"IN3": 64.0, "IN1": 130.0, "IN2": 196.0}; IN_Y_N = -14.6               # Grok b input-board placement, unchanged
z_deck_bot = Z_TOP + P["so_m3_len"]; z_deck_top = z_deck_bot + P["deck_t"]; Z_IN = z_deck_top + P["in_boss"]
stepI_r = stepI.rotate(Axis.Z, 90)
def in_hole(n, hx, hy): return (IN_X[n] + hy, IN_Y_N - 66.0 + hx)
for n, x in IN_X.items():
    addp(f"input-board-{n}", stepI_r.translate(Vector(x, IN_Y_N - 66.0, Z_IN)), (0.1, 0.35, 0.55), "input-board STEP from Grok pack, turned 90 deg (Grok b placement)", step=False)

# ---------------- footprint ----------------
ec = P["edge_clear"]
LX0 = -ec; LX1 = X0["A2"] + 72.39 + ec; LY1 = ec; LY0 = P["lid_y0"]
pt = P["plate_t"]; zf0 = -pt - P["fin_h"]; zfoot = zf0 - P["foot_h"]
sink = dblock(LX0, LX1, LY0, LY1, -pt, 0, r=P["corner_r"])
PED = {"A": [(-1.905, 13.132, 11.379, 14.021), (-1.981, 10.922, -13.970, -11.227)],
       "B": [(-12.22, 12.32, 11.15, 14.07), (-12.22, 12.32, -14.07, -11.15), (53.623, 56.265, -27.415, 46.417)]}
pads = []
for n in ("B", "A1", "A2"):
    for (a, b, c, d) in PED["B" if n == "B" else "A"]:
        (xa, ya), (xb, yb) = W(n, a - 1.5, c - 1.5), W(n, b + 1.5, d + 1.5)
        sink = sink.fuse(box(xa, xb, ya, yb, 0, P["ped_h"])); pads.append(box(xa, xb, ya, yb, P["ped_h"], Z_BOT))
HOLES_AB = {"H1": (-33.02, 21.59), "H2": (26.67, -21.59), "H3": (-21.082, -21.59), "H4": (26.67, 21.59)}
HOLES_B = {"H5": (69.044, -10.684), "H6": (69.044, 35.896)}
BOSS = []
for n in ("B", "A1", "A2"):
    hs = dict(HOLES_AB); hs.update(HOLES_B if n == "B" else {})
    for h, (x, y) in hs.items(): BOSS.append((n, h, W(n, x, y)))
for n, h, (X, Y) in BOSS: sink = sink.fuse(cyl(6.0, (X, Y, 0), Z_BOT))
for n, h, (X, Y) in BOSS: sink = sink.cut(cyl(2.5, (X, Y, Z_BOT - 8.0), 8.01))

# ---------------- feet (reinforced): hex AF24 posts with two webs along the plate edges ----------------
FEET = [(LX0 + 14, LY0 + 14, 1, 1), (LX0 + 14, LY1 - 14, 1, -1), (LX1 - 14, LY0 + 14, -1, 1), (LX1 - 14, LY1 - 14, -1, -1)]
feet = None; foot_keepout = []
for (X, Y, sx, sy) in FEET:
    f = hexp(P["foot_af"], (X, Y, zfoot), -zfoot - pt + 0.01)
    f = f.fuse(box(X, X + sx * P["foot_web_L"], Y - P["foot_web_t"] / 2, Y + P["foot_web_t"] / 2, zf0, -pt))
    f = f.fuse(box(X - P["foot_web_t"] / 2, X + P["foot_web_t"] / 2, Y, Y + sy * P["foot_web_L"], zf0, -pt))
    feet = f if feet is None else feet.fuse(f)
    foot_keepout.append(box(X - 15 * sx, X + sx * (P["foot_web_L"] + 3), Y - 15 * sy, Y + sy * (P["foot_web_L"] + 3), zf0 - 1, -pt))
# ---------------- fins + fans ----------------
fe = P["fin_edge"]; fan_info = {}; PRE_SCR = []
if VAR == "F1":
    # Grok's straight east-west fins, stopped at a 16 mm fan bay at the east end; 2 x Sunon 30x30x10 inside the outline, push west
    bay_x0 = LX1 - fe - 18.0
    fins = []
    y = LY0 + fe
    while y + P["fin_t"] <= LY1 - fe + 1e-6:
        fins.append(box(LX0 + fe + 16, bay_x0, y, y + P["fin_t"], zf0, -pt)); y += P["fin_pitch"]
    finf = Compound(fins)
    fan_y = [(LY0 + LY1) / 2 - 16, (LY0 + LY1) / 2 + 16]; fan_z = zf0 + 15.0   # both fans near mid, clear of the east-mid foot web
    wall_x = bay_x0 + 1.0                                         # 3 mm fan wall (part of the sink), fans bolt to its east face
    fwall = box(wall_x, wall_x + 3.0, LY0 + fe + 8, LY1 - fe - 8, zf0, -pt)
    for fy in fan_y: fwall = fwall.cut(cyl(28.0, (wall_x - 1, fy, fan_z), 5.0, (1, 0, 0)))
    for fy in fan_y:
        for dy in (-12, 12):
            for dz in (-12, 12): fwall = fwall.cut(cyl(2.5, (wall_x - 1, fy + dy, fan_z + dz), 5.0, (1, 0, 0)))   # M3 tap for fan screws (Sunon hole pitch 24, spec drawing)
    finf = finf.fuse(fwall)
    fan_info = dict(kind="2 x Sunon MF30101V1-1000U-A99", x=(wall_x + 3.0, wall_x + 13.0), y=fan_y, z=fan_z)
else:
    # F2: one Noctua NF-A6x15 (60x60x15) blowing UP, in a pocket in the fin field; swept radial fins guide air outward
    FCX, FCY = 150.0, -52.0
    ft = 2.5; r0 = 31.0
    xs0, xs1, ys0, ys1 = LX0 + fe, LX1 - fe, LY0 + fe, LY1 - fe
    def spiral(theta0, rstart):
        pts = []; r = rstart
        while True:
            th = theta0 + 0.55 * math.log(r / r0)
            x, y = FCX + r * math.cos(th), FCY + r * math.sin(th)
            if not (xs0 + 1 < x < xs1 - 1 and ys0 + 1 < y < ys1 - 1): break
            pts.append((x, y)); r += 5.0
        return pts
    fins = []
    def spiral_dense(theta0, rstart, step=2.0):
        pts = []; r = rstart
        while True:
            th = theta0 + 0.55 * math.log(r / r0)
            x, y = FCX + r * math.cos(th), FCY + r * math.sin(th)
            if not (xs0 + 1 < x < xs1 - 1 and ys0 + 1 < y < ys1 - 1): break
            pts.append((x, y)); r += step
        return pts
    def fin_from(pts):
        """SMOOTH fin (Dan 2026-11-13): tangent-continuous spline centreline, constant thickness ft by a 2-D offset with
        round (arc) ends, extruded to the fin depth; fin tips filleted 1.0. One smooth curve for the 3-axis toolpath."""
        c = Spline(*[Vector(x, y, -pt) for (x, y) in pts])
        w2 = Wire([c]).offset_2d(ft / 2, kind=Kind.ARC, side=Side.BOTH, closed=False)
        f = Face(w2)
        sol = extrude(f, amount=-(zf0 - (-pt))).solid() if False else Solid.extrude(f, Vector(0, 0, zf0 + pt))
        try:
            sol = sol.fillet(1.0, sol.faces().sort_by(Axis.Z)[0].edges())          # fin tip edges
        except Exception:
            pass
        return sol
    N = 24; fin_len = 0.0
    for i in range(N):
        p = spiral_dense(2 * math.pi * i / N, r0)
        if len(p) > 3: fins.append(fin_from(p)); fin_len += sum(math.dist(a_, b_) for a_, b_ in zip(p[:-1], p[1:]))
        p = spiral_dense(2 * math.pi * (i + 0.5) / N, 62.0)                 # splitter fins between the long ones
        if len(p) > 3: fins.append(fin_from(p)); fin_len += sum(math.dist(a_, b_) for a_, b_ in zip(p[:-1], p[1:]))
    fan_info["fin_len_total_mm"] = round(fin_len, 1); fan_info["fin_t"] = ft; fan_info["N"] = N
    # narrowest channel: log spiral (tan psi = 0.55): normal pitch = r * (2 pi / N) * cos(psi); long fins from r0, splitters from r 62
    psi = math.atan(0.55)
    fan_info["min_channel_mm"] = round(min(r0 * 2 * math.pi / N * math.cos(psi), 62.0 * math.pi / N * math.cos(psi)) - ft, 2)
    finf = Compound(fins)
    pocket = dblock(FCX - 31.5, FCX + 31.5, FCY - 31.5, FCY + 31.5, zf0 - 1, zf0 + 18.0, r=4.0)   # NF-A6x15 model is 16 tall (frame Y -0.5..15.5) + 2 recess
    fan_info.update(kind="1 x Noctua NF-A6x15 PWM", c=(FCX, FCY), z_bottom=zf0 + 2.0, z_top=zf0 + 18.0)
finf = finf.cut(*foot_keepout) if foot_keepout else finf
sink = sink.fuse(finf, feet)
if VAR == "F2":
    sink = sink.cut(pocket)
    for dx in (-25, 25):
        for dy in (-25, 25):                                          # 4 posts from the plate to the fan top face, M3 tapped (Noctua 50 mm hole pitch)
            sink = sink.fuse(cyl(8.0, (FCX + dx, FCY + dy, zf0 + 18.0), -pt - zf0 - 18.0))
            sink = sink.cut(cyl(2.5, (FCX + dx, FCY + dy, zf0 + 17.9), 8.0))
    sink = sink.cut(cyl(2.5, (FCX, FCY, -pt - 0.1), 7.0))           # M3 tap drill 7 deep: flow-cone screw
    # flow cone (Dan 2026-11-13): MJF PA12 paraboloid hanging from the plate underside over the fan hub, apex 1.5 above
    # the fan outlet face; turns the fan's axial (upward) flow outward into the swept fin channels. r = R * sqrt((z - z_apex) / H)
    z_apex = fan_info["z_top"] + 1.5; Hc = -pt - z_apex; Rc = 26.0
    prof = [(Rc * math.sqrt(t), z_apex + t * Hc) for t in [i / 16 for i in range(17)]]
    sp = Spline(*[Vector(FCX + r_, FCY, z_) for (r_, z_) in prof])
    wr = Wire([sp, Line((FCX + Rc, FCY, -pt), (FCX, FCY, -pt)), Line((FCX, FCY, -pt), (FCX, FCY, z_apex))])
    cone = revolve(Face(wr), Axis((FCX, FCY, 0), (0, 0, 1)), 360).solid()
    cone = cone.cut(cyl(3.4, (FCX, FCY, z_apex - 1), Hc + 2)).cut(cyl(6.2, (FCX, FCY, z_apex - 1), 5.0))   # M3 clearance + head counterbore from the apex
    flow_cone = cone
    PRE_SCR.append(("SSH-M3-0.5 x 12", shcs("M3", 12.0, (FCX, FCY, z_apex + 4.0), down=False)))
    fan_info.update(cone=dict(R=Rc, H=round(Hc, 2), apex_gap=1.5, z_apex=round(z_apex, 2)))
for (X, Y, sx, sy) in FEET:
    sink = sink.cut(cyl(6.6, (X, Y, zfoot - 1), -zfoot + 2))           # M6 clearance, bolt-through mounting
LID_SCREWS = []
nx = 5
for i in range(nx):
    X = LX0 + 30 + i * (LX1 - LX0 - 60) / (nx - 1); LID_SCREWS += [(X, LY1 - 5.0)]
LID_SCREWS += [(X, LY0 + 5.0) for X in (20.0, 66.0, 147.0, 222.0, LX1 - 20.0)]   # front: clear of the X1/X2/USB turrets and flanges
LID_SCREWS += [(LX0 + 5.0, (LY0 + LY1) / 2), (LX1 - 5.0, (LY0 + LY1) / 2)]
for (X, Y) in LID_SCREWS:
    sink = sink.cut(cyl(4.5, (X, Y, -pt - 1), pt + 2)); sink = sink.cut(cyl(7.5, (X, Y, -pt - 1), 5.0))   # counterbore to Z -4
addp("heat-sink", sink, (0.72, 0.72, 0.76), f"6061-T6 aluminium, one machined part (3-axis), {VAR}; reinforced hex feet; all sizes ASSUMED")
if VAR == "F2": addp("flow-cone-PA12", flow_cone, (0.22, 0.22, 0.25), "MJF PA12 paraboloid flow cone R26 x 10.5, apex 1.5 above the Noctua outlet, M3 x 12 into the plate (Dan 2026-11-13)")
addp("gap-pads", Compound(pads), (0.95, 0.5, 0.6), "insulating gap pad 1.0, product TBD")

# ---------------- vendor models ----------------
def vstep(rel): return import_step(os.path.join(VENDOR, rel))
vend = {}
if VAR == "F1":
    # Sunon MF30101V1-1000U-A99: NO maker STEP found (Sunon site / distributors checked 2026-11-12);
    # modelled from Sunon spec D03033580G-01 dims: 30 x 30 x 10, 4 holes 3.4 at 24 pitch, hub dia 12
    fans = []
    for fy in fan_info["y"]:
        x0 = fan_info["x"][0]
        f = box(x0, x0 + 10, fy - 15, fy + 15, fan_z - 15, fan_z + 15).cut(cyl(28.6, (x0 - 1, fy, fan_z), 12, (1, 0, 0)))
        f = f.fuse(cyl(12.0, (x0, fy, fan_z), 10, (1, 0, 0)))
        for k in range(7):
            a = 2 * math.pi * k / 7
            f = f.fuse(Pos(x0 + 5, fy + 9.5 * math.cos(a), fan_z + 9.5 * math.sin(a)) * Rot(a * 180 / math.pi, 25, 0) * Box(1.2, 8.5, 6))
        for dy in (-12, 12):
            for dz in (-12, 12): f = f.cut(cyl(3.4, (x0 - 1, fy + dy, fan_z + dz), 12, (1, 0, 0)))
        fans.append(f)
    addp("fans-Sunon-MF30101V1", Compound(fans), (0.1, 0.1, 0.1), "MODELLED FROM DRAWING (no maker STEP found): Sunon spec D03033580G-01, 30x30x10")
    for fy in fan_info["y"]:
        for dy in (-12, 12):
            for dz in (-12, 12):
                vend.setdefault("fan-screws", []).append(shcs("M3", 16.0, (fan_info["x"][1], fy + dy, fan_z + dz), down=True).rotate(Axis.Y, 0))
else:
    nf = vstep("noctua_NF-A6x15/NF-A6x15_Public-CAD.stp")          # frame: X -30..30, Y -0.5..15.5 (axis), Z -30..30
    nf = nf.rotate(Axis.X, 90)                                      # axis Y -> Z
    b = bbx(nf)
    nf = nf.translate(Vector(fan_info["c"][0] - (b.xmin + b.xmax) / 2, fan_info["c"][1] - (b.ymin + b.ymax) / 2, fan_info["z_bottom"] - b.zmin))
    addp("vendor-fan-Noctua-NF-A6x15", nf, (0.55, 0.35, 0.25), "Noctua NF-A6x15 public CAD STEP (noctua.at downloads), blowing up into the fins")
# X1 / X2 receptacles + mating plugs: TE customer view models (te.com, CVM_*), axis local +Z = mating face
def place_conn(s, X, Zc, front_y_local0):
    # local Z -> world -Y (outward), local Y -> world Z (flats top/bottom); local z=-26.16 (flange front face) on the wall inner face
    s = s.rotate(Axis.X, 90)                                         # (x,y,z) -> (x,-z,y)
    return s.translate(Vector(X, front_y_local0, Zc))
TZ = P["turret_z"]; WALL_IN = LY0 + P["wall"]
YOFF = WALL_IN - 26.16                                               # world Y of the connector local z=0 (mating face) = WALL_IN - 26.16
CONN = {"X1": 108.0, "X2": 186.0}; USB_X = 246.0
x1 = place_conn(vstep("HD34-24-21SN/c-hd34-24-21sn-p1-3d.stp"), CONN["X1"], TZ, YOFF)
x2 = place_conn(vstep("HDP24-24-47SE-L017/c-hdp24-24-47se-l017-b-3d.stp"), CONN["X2"], TZ, YOFF)
addp("vendor-X1-HD34-24-21SN", x1, (0.6, 0.6, 0.62), "TE CVM_HD34-24-21SN STEP (te.com), panel-nut mount, flange inside the wall")
addp("vendor-X2-HDP24-24-47SE-L017", x2, (0.1, 0.1, 0.1), "TE CVM_HDP24-24-47SE-L017 STEP (te.com), panel-nut mount, flange inside the wall")
# mating plugs, mated position APPROXIMATE (plug +Z end placed 16 mm in from the receptacle mating face)
def place_plug(s, X):
    s = s.rotate(Axis.X, -90)                                        # local +Z -> world +Y (toward the box)
    b = bbx(s); return s.translate(Vector(X, YOFF + 16.0 - b.ymax, TZ))
p1 = place_plug(vstep("HD36-24-21PN/c-hd36-24-21pn-d1-3d.stp"), CONN["X1"])
p2 = place_plug(vstep("HDP26-24-47PE-L015/c-hdp26-24-47pe-l015-c-3d.stp"), CONN["X2"])
addp("vendor-plug-HD36-24-21PN", p1, (0.25, 0.25, 0.27), "TE CVM_HD36-24-21PN STEP; mated position approximate", step=False)
addp("vendor-plug-HDP26-24-47PE-L015", p2, (0.25, 0.25, 0.27), "TE CVM_HDP26-24-47PE-L015 STEP; mated position approximate", step=False)
# panel nuts 2411-001-2405 + lock washers 2414-001-2486 (TE spec 0425-021-0000): hex AF from the 1-7/8 in socket = 47.6; thickness 6 ASSUMED
nuts = []
for X in CONN.values():
    nuts.append(hexp(47.6, (X, LY0, TZ), 6.0, axis=(0, -1, 0), rot=0).cut(cyl(42.9, (X, LY0 + 1, TZ), 9.0, (0, -1, 0))))
addp("panel-nuts-2411-001-2405", Compound(nuts), (0.12, 0.12, 0.12), "TE 2411-001-2405 panel nut (spec 0425-021-0000): AF 47.6 from tool size; thickness 6 ASSUMED (no STEP)")
# USB-C bulkhead: Amphenol LTW UC-00PMFY-SC7001 (no STEP reachable: Digi-Key Cloudflare, LTW site redirect);
# MODELLED FROM CATALOG VALUES (UC series catalog): cut-out D 20.8 with 19.4 flat, panel <= 4.0, square flange 25.4, nut OD 25.4; depths ASSUMED
ub = box(USB_X - 11, USB_X + 11, WALL_IN, WALL_IN + 29.3, P["usb_z"] - 11, P["usb_z"] + 11)
ub = ub.fuse(box(USB_X - 12.7, USB_X + 12.7, WALL_IN, WALL_IN + 2.0, P["usb_z"] - 12.7, P["usb_z"] + 12.7))
ub = ub.fuse(cyl(20.6, (USB_X, WALL_IN, P["usb_z"]), 16.0, (0, -1, 0)).cut(box(USB_X - 12, USB_X + 12, WALL_IN + 1, LY0 - 20, P["usb_z"] + 9.0, P["usb_z"] + 12))).fuse(hexp(22.0, (USB_X, LY0, P["usb_z"]), 5.0, axis=(0, -1, 0), rot=0))
ub = ub.cut(box(USB_X - 4.5, USB_X + 4.5, LY0 - 14, LY0 - 3, P["usb_z"] - 1.7, P["usb_z"] + 1.7))
addp("usbc-bulkhead-UC-00PMFY-SC7001", ub, (0.15, 0.15, 0.15), "MODELLED FROM CATALOG (Amphenol LTW UC series): no maker STEP reachable; depths ASSUMED")
hub = vstep("adafruit_5997_5997-CH334F-4-Port-Hub.step")
hub = hub.rotate(Axis.Z, 90); b = bbx(hub)                         # long axis along X
HUB_Z = 4.0
hub = hub.translate(Vector(-2.0 - b.xmin, WALL_IN + 7.5 - b.ymin, HUB_Z - b.zmin))   # front-west corner, south of board B, clear of the lid-screw boss
addp("vendor-hub-Adafruit-5997", hub, (0.1, 0.1, 0.4), "Adafruit 5997 CH334F 4-port hub, Adafruit_CAD_Parts STEP (GitHub)")
hb = bbx(hub)
hubst = [cyl(5.0, (x, y, 0.0), HUB_Z) for x in (hb.xmin + 2.5, hb.xmax - 2.5) for y in (hb.ymin + 2.5, hb.ymax - 2.5)]
addp("hub-standoffs-M2.5x4", Compound(hubst), (0.3, 0.3, 0.33), "M2.5 standoffs 4 mm on the sink field, PN TBD")

# ---------------- terminals: copper bosses (v3b) on board B J1/J3 and T1-T4; copper bars to A1/A2 ----------------
M6TOP = Z_BOT + max(bbx(so).zmax for so in stepB.solids() if abs(bbx(so).xlen - 10) < 0.6)
TTOP = Z_BOT + 4.73
FEED = {"BATT+": W("B", -24.638, 27.178), "GND": W("B", -30.48, -27.178)}
FEED_A = {n: {"BATT+": W(n, -24.638, 27.178), "GND": W(n, -30.48, -27.178)} for n in ("A1", "A2")}
OUTT = {"OUT1": W("B", 12, 4.75), "OUT3": W("B", 12, -4.75), "OUT2": W("B", -12, 4.75), "OUT4": W("B", -12, -4.75)}
T58 = {f"T{i}": W("B", 68.394, y) for i, y in zip((5, 6, 7, 8), (-23.584, -0.294, 22.996, 46.286))}
ZB0, ZB1 = M6TOP, M6TOP + P["bar_t"]
SO_EXCL = []
# deck standoffs (Grok b rule) - computed first so the bar can be notched around them
DX0, DX1 = 62.0, 262.0; DY1, DY0 = IN_Y_N + 4.0, IN_Y_N - 66.0 - 4.0
SO = [(n, h, (X, Y)) for (n, h, (X, Y)) in BOSS if DX0 + 3 < X < DX1 - 3 and DY0 + 3 < Y < DY1 - 3]
def bar(points_x, yc, w, end_pts):
    xa, xb = min(points_x) - 8.5, max(points_x) + 10.0
    b_ = dblock(xa, xb, yc - w / 2, yc + w / 2, ZB0, ZB1, r=4.0)
    for (X, Y) in end_pts: b_ = b_.cut(cyl(6.6, (X, Y, ZB0 - 1), P["bar_t"] + 2))   # M6 clearance at each terminal
    for (n, h, (X, Y)) in SO:
        if xa < X < xb and yc - w / 2 - 6 < Y < yc + w / 2 + 6:
            b_ = b_.cut(cyl(11.0, (X, Y, ZB0 - 1), P["bar_t"] + 2))                   # standoff pass-through: 11 dia (insulating sleeve 1.5 wall)
    return b_
bp = [FEED["BATT+"], FEED_A["A1"]["BATT+"], FEED_A["A2"]["BATT+"]]
gp = [FEED["GND"], FEED_A["A1"]["GND"], FEED_A["A2"]["GND"]]
batt = bar([p[0] for p in bp], P["batt_yc"], P["batt_w"], bp)
gnd = bar([p[0] for p in gp], P["gnd_yc"], P["gnd_w"], gp)
addp("copper-bar-BATT", batt, (0.85, 0.45, 0.2), f"C110 copper bar {P['batt_w']}x{P['bar_t']}, B J1 -> A1 J1 -> A2 J1; insulating film under, sleeves at standoffs; ASSUMED")
addp("copper-bar-GND", gnd, (0.6, 0.35, 0.2), f"C110 copper bar {P['gnd_w']}x{P['bar_t']}, B J3 -> A1 J2 -> A2 J2; ASSUMED")
scr = list(PRE_SCR)
bosses6, bosses4 = [], []
LID_COLLAR = {}
for k, (X, Y) in FEED.items():
    L6 = P["collar_top"] + 1.0 - ZB1                                # boss top 1 mm above the collar top (Grok ext top 33.23)
    bo = hexp(P["boss6_af"], (X, Y, ZB1), L6).cut(cyl(5.0, (X, Y, ZB1 + L6 - 12), 12.1)).cut(cyl(5.0, (X, Y, ZB1 - 0.1), 10.1))  # M6 tap drill 5.0 both ends
    bosses6.append(bo)
    # boss 15 tall (top 1 mm over the collar): stud 6 into the bottom, SSH-M6x10 lug screw 8 into the top, 1 mm gap between
    scr.append(("M6 stud 19 (threaded rod)", cyl(6.0, (X, Y, M6TOP - 8.0), 8.0 + P["bar_t"] + 6.0)))
    scr.append(("SSH-M6-1 x 10", shcs("M6", 10.0, (X, Y, ZB1 + L6 + P["lug_t"]))))
for n in ("A1", "A2"):
    for k, (X, Y) in FEED_A[n].items():
        scr.append(("SSH-M6-1 x 16", shcs("M6", 16.0, (X, Y, ZB1))))
addp("copper-boss-M6-BATT-GND", Compound(bosses6), (0.85, 0.5, 0.25), f"custom C110 copper hex boss AF{P['boss6_af']:.0f}, M6 female both ends, 3-axis machinable from hex bar")
# ---- OUT1-4: copper OFFSET RISERS held in ONE G10 carrier (Dan d1a / c1b, 2026-11-13) ----
# Each riser is a C110 obround block: foot on board B T1-T4 (Wurth REDCUBE 74650074R, M4, 2.5 mm thread, max 1.2 N*m per datasheet),
# lug seat offset 8+ mm away (taller AND spread). Two tiers: west pair (OUT2/OUT4) low, east pair (OUT1/OUT3) high, so the east pair's
# wires pass over the carrier ridge between the west lugs. The G10 carrier is keyed on the risers (obround slots: they can't turn),
# holds every lug in its own slot with solid G10 walls between, and is bolted to M3 x 8 M-F standoffs on board B H2/H4,
# so lug-screw torque goes into the carrier and the heat-sink posts, not into the soldered REDCUBE terminals.
Z_CB = Z_TOP + 8.0                                   # carrier bottom = top of the M3 x 8 standoffs (below the copper bars, ZB0)
Z_L, Z_U = P["out_seat_lo"], P["out_seat_hi"]
SEAT = {"OUT2": (29.5, -45.3, Z_L), "OUT4": (29.5, -21.24, Z_L), "OUT1": (44.0, -43.6, Z_U), "OUT3": (44.0, -22.94, Z_U)}   # seat >= 8 mm from the T centre (foot-screw head clears the column); 6.5 mm lane between the pairs for the B J6 wires
LUGANG = {"OUT2": 165.0, "OUT4": 195.0, "OUT1": 159.0, "OUT3": 201.0}   # upper barrels end 8 mm apart (2 mm air), clear of the lower screw heads
LANE = {"OUT2": -41.0, "OUT1": -37.3, "OUT3": -29.2, "OUT4": -25.5}
RR = P["riser_r"]
def obround(p, q, r, z0, z1):
    a_, b_ = Vector(p[0], p[1], 0), Vector(q[0], q[1], 0); d = b_ - a_; L = d.length; ang = math.degrees(math.atan2(d.Y, d.X)); m = (a_ + b_) * 0.5
    return extrude(Pos(m.X, m.Y, z0) * Rot(0, 0, ang) * SlotCenterToCenter(L, 2 * r), amount=z1 - z0).solid()
def slot_along(x, y, ang, wd, L, z0, z1):
    pl = Plane(origin=(x, y, z0), x_dir=(math.cos(math.radians(ang)), math.sin(math.radians(ang)), 0), z_dir=(0, 0, 1))
    return extrude(pl * Pos(L / 2, 0) * Rectangle(L, wd), amount=z1 - z0).solid()
risers = []
for k, (sx, sy, sz) in SEAT.items():
    tx, ty = OUTT[k]; H = sz - TTOP
    rb = obround((tx, ty), (sx, sy), RR, TTOP, TTOP + P["riser_foot"]).fuse(cyl(2 * RR, (sx, sy, TTOP), H))   # foot arm 4 thick + seat column
    rb = rb.cut(cyl(4.5, (tx, ty, TTOP - 0.1), P["riser_foot"] + 0.2))                                     # M4 clearance at the foot (screw head sits on the arm)
    rb = rb.cut(cyl(3.3, (sx, sy, sz - 10.0), 10.1))                                                      # M4 tap drill 3.3 x 10 deep (lug screw)
    risers.append(rb)
    scr.append(("SSH-M4-0.7 x 6", shcs("M4", 6.0, (tx, ty, TTOP + P["riser_foot"]))))                        # foot screw: 2.0 into the 2.5 REDCUBE thread, max 1.2 N*m
    scr.append(("SSH-M4-0.7 x 8", shcs("M4", 8.0, (sx, sy, sz + P["out_lug_t"]))))                            # lug screw into the copper seat (7 mm engagement)
addp("copper-risers-OUT1-4", Compound(risers), (0.85, 0.5, 0.25), "custom C110 copper offset risers (foot arm R4 x 4 + seat column dia 8, 3-axis from 20 mm square bar): M4 foot to REDCUBE T1-T4, lug seat M4 x 10 tapped (Dan d1a)")
CX0, CXM, CX1, CY0, CY1 = 20.0, 36.5, 58.0, -52.0, -14.0
ZCL, ZCU = Z_L + P["pocket_d"], Z_U + P["pocket_d"]
car = dblock(CX0, CXM + 1.0, CY0, CY1, Z_CB, ZCL, r=3)
car = car.fuse(dblock(CXM, CX1, CY0 + 2, CY1 - 2, Z_CB, ZCU, r=3))
ANCH = [W("B", 26.67, -21.59), W("B", 26.67, 21.59)]                 # board B H2, H4 (H1 / H3 sit inside the BATT / GND collars)
for (X, Y) in ANCH:
    yA, yB = (CY1 - 8, Y + 6) if Y > CY1 - 3 else (Y - 6, CY0 + 8)
    car = car.fuse(dblock(X - 14, X + 6, min(yA, yB), max(yA, yB), Z_CB, Z_CB + P["ear_t"], r=3))
for k, (sx, sy, sz) in SEAT.items():
    tx, ty = OUTT[k]
    car = car.cut(obround((tx, ty), (sx, sy), RR + 0.1, Z_CB - 1, 80))                                   # key slot = riser + 0.1
    car = car.cut(cyl(11.0, (sx, sy, sz), 40)).cut(slot_along(sx, sy, LUGANG[k], P["out_lug_w"] + 1.0, 40.0, sz, 80))   # lug ring pocket + tongue slot
for (X, Y) in ANCH:
    car = car.cut(cyl(3.4, (X, Y, Z_CB - 1), 20)).cut(cyl(6.5, (X, Y, Z_CB + P["ear_t"] - 3.2), 10))
    scr.append(("SSH-M3-0.5 x 8", shcs("M3", 8.0, (X, Y, Z_CB + P["ear_t"] - 3.2))))
addp("carrier-G10-OUT1-4", car, (0.75, 0.78, 0.55), "G10 / FR4 carrier (3-axis): keys the 4 copper risers, separates the lugs with solid walls, takes lug torque; bolted to M3 x 8 standoffs on board B H2/H4 (Dan d1a)")
sos2 = [standoff_mf(5.5, 8.0, 3.0, 6.0, 6.0, (X, Y, Z_TOP)) for (X, Y) in ANCH]
addp("standoffs-M3x8-MF-carrier", Compound(sos2), (0.8, 0.7, 0.3), "M3 M-F hex standoff AF5.5 x 8 (carrier anchors, replace the board B H2/H4 screws; male end into the sink posts), PN TBD")
for nm in ("copper-bar-BATT", "copper-bar-GND"):                        # standoff pass-through at the bar edges (insulating sleeve)
    sh = parts[nm]["shape"]
    for (X, Y) in ANCH: sh = sh.cut(cyl(11.0, (X, Y, ZB0 - 1), P["bar_t"] + 2))
    parts[nm]["shape"] = one(sh)
M6_EXT_TOP = P["collar_top"] + 1.0; M4_EXT_TOP = Z_U
# OUT1-4 ring lugs (Phoenix Contact 3240083, M4, 10-14 AWG; modelled from catalogue dims: 8.0 wide, 17.5 long, 0.99 thick) + 10 AWG wires to the west lid edge
def ring_lug(X, Y, ang, z):
    t, wdt, Lg, bd, bL = P["out_lug_t"], P["out_lug_w"], P["out_lug_L"], P["out_barrel_d"], P["out_barrel_L"]
    pl = Plane(origin=(X, Y, z), x_dir=(math.cos(math.radians(ang)), math.sin(math.radians(ang)), 0), z_dir=(0, 0, 1))
    tongue = extrude(pl * Circle(wdt / 2), amount=t).solid()
    tongue = tongue.fuse(extrude(pl * Pos((Lg - bL) / 2, 0) * Rectangle(Lg - bL, bd), amount=t).solid())
    tongue = tongue.cut(cyl(4.3, (X, Y, z - 1), t + 2))
    d = Vector(math.cos(math.radians(ang)), math.sin(math.radians(ang)), 0)
    b0 = Vector(X, Y, z + bd / 2) + d * (Lg - bL)
    return tongue.fuse(Solid.make_cylinder(bd / 2, bL, Plane(origin=b0, z_dir=d))), b0 + d * bL
XE = LX0 - 15.0
lugs, owires = [], []
for k, (sx, sy, sz) in SEAT.items():
    lg, e = ring_lug(sx, sy, LUGANG[k], sz); lugs.append(lg)
    wz = sz + P["out_barrel_d"] / 2
    owires.append(tube([(e.X, e.Y, wz), (min(e.X - 6.0, 20.0), LANE[k], wz), (XE, LANE[k], wz)], P["out_wire_d"]))
addp("ring-lugs-OUT1-4", Compound(lugs), (0.85, 0.6, 0.3), "Phoenix Contact 3240083 ring terminal M4, 10-14 AWG (no maker CAD reachable; modelled from catalogue dims 8.0 x 17.5 x 0.99, barrel OD 6 ASSUMED)", step=False)
addp("wires-OUT1-4-10AWG", Compound(owires), (0.75, 0.1, 0.1), "OUT1-4 wires 10 AWG GXL (OD 4.2 ASSUMED), 31 A each, two tiers out through the lid wire-way to the west edge; ASSUMED routing", step=False)
# T5-T8 ring lugs + M4 screws (v2b), wires to X1
for k, (X, Y) in T58.items(): scr.append(("SSH-M4-0.7 x 8", shcs("M4", 8.0, (X, Y, TTOP + P["lug_t"]))))

# ---------------- input deck + standoffs (Grok b, unchanged) ----------------
deck = dblock(DX0, DX1, DY0, DY1, z_deck_bot, z_deck_top, r=6)
for n, x in IN_X.items(): deck = deck.cut(dblock(x + 9, x + 55, IN_Y_N - 58, IN_Y_N - 10, z_deck_bot - 1, z_deck_top + 1, r=5))
in_pts = []
for n in IN_X:
    for (hx, hy) in [(4, 60), (62, 4)]:
        X, Y = in_hole(n, hx, hy); in_pts.append((X, Y)); deck = deck.fuse(cyl(7.0, (X, Y, z_deck_top), P["in_boss"]))
for (X, Y) in in_pts: deck = deck.cut(cyl(4.0, (X, Y, z_deck_top - 2.99), P["in_boss"] + 3.0))
for n, h, (X, Y) in SO: deck = deck.cut(cyl(3.4, (X, Y, z_deck_bot - 1), P["deck_t"] + 2))
addp("input-deck", deck, (0.3, 0.3, 0.33), "MJF PA12 frame for the 3 input boards (Grok b)")
from screwtool_twin import standoff_mf
sos = [standoff_mf(5.5, P["so_m3_len"], 3.0, 6.0, 6.0, (X, Y, Z_TOP)) for (n, h, (X, Y)) in SO]
addp("standoffs-M3x25-MF", Compound(sos), (0.8, 0.7, 0.3), "M3 M-F hex standoff AF5.5 x 25, PN TBD")
for n, h, (X, Y) in SO: scr.append(("SSH-M3-0.5 x 8", shcs("M3", 8.0, (X, Y, z_deck_top))))
so_set = {(n, h) for (n, h, _) in SO}
so_set |= {("B", "H2"), ("B", "H4")}                 # carrier standoffs replace these board screws
for n, h, (X, Y) in BOSS:
    if (n, h) not in so_set: scr.append(("SSH-M3-0.5 x 8", shcs("M3", 8.0, (X, Y, Z_TOP))))
for (X, Y) in in_pts: scr.append(("SSH-M3-0.5 x 8", shcs("M3", 8.0, (X, Y, Z_IN + 1.51))))

# ---------------- wiring (flat taped ribbons, ASSUMED harness form) ----------------
REAR = {k: (X, WALL_IN + 2.54 + 19.6 + 4.0) for k, X in CONN.items()}   # Y just behind the X2 grommet (X1 rear ends further south)
YR = REAR["X1"][1]
zr = Z_TOP + 7.0                                   # A ribbons over the boards: under the bars (ZB0) and the deck
wires = []
for n, xc, xe in (("A1", None, CONN["X1"] - 6.0), ("A2", 223.0, CONN["X1"] + 6.0)):
    cx, cy = W(n, 0, 0); xc = xc or cx
    via = [(165.0, -99.5, zr + 6.0)] if n == "A2" else []   # A2 ribbon passes behind X2's rear body (y -107.4) with 1 mm to spare
    wires.append(ribbon([(cx, cy, Z_TOP + 2.5), (xc, cy - 8, zr), (xc, -97.0, zr)] + via + [(xe, YR, TZ - 8)], 14.0, P["ribbon_t"]))   # 12 wires (8 x 16 AWG + 4 x 20 AWG) in two layers
bx_, by_ = W("B", -1.5, -1.5)                      # B J6 pads (CAN + IN1/2) -> X2: low along the sink field south of the boards
jx = (SEAT["OUT2"][0] + RR + SEAT["OUT1"][0] - RR) / 2   # lane between the OUT2/OUT4 and OUT1/OUT3 copper risers (d1a)
wires.append(ribbon([(bx_, by_, Z_TOP + 2.0), (jx, by_, Z_TOP + 5.0), (jx, -60.0, Z_TOP + 5.0), (jx, -103.0, Z_TOP + 6.0), (jx, -106.0, 4.4), (CONN["X2"] - 6, -105.0, 4.4), (CONN["X2"] - 6, -103.5, TZ + 4)], 3.5, 3.5))   # 4 x 20 AWG round bundle
tx = 96.5                                          # B T5-T8 wires (ring lugs on the M4 terminals, x 106.2) gathered west of the H5/H6 standoffs
wires.append(ribbon([(tx, T58["T5"][1], 16.0), (tx, -97.0, 16.0), (CONN["X1"] + 14, YR, 19.0)], 12.0, 2.5))
for n, x in IN_X.items():                          # input-board J2 wires -> X2, from the deck south edge
    wires.append(ribbon([(x + 33, DY0 + 2, z_deck_top + 8), (x + 33, DY0 - 8, TZ + 14), (CONN["X2"] + 8, YR, TZ + 14)], 10.0, 3.0))
usbc = []
UR = WALL_IN + 29.3
# bulkhead rear -> north 6, drop to the sink field, back south UNDER the bulkhead body (body bottom z 13), west to the hub
usbc.append(tube([(USB_X, UR, P["usb_z"]), (USB_X, -95.0, P["usb_z"]), (80.0, -95.0, P["usb_z"]), (68.0, -95.0, 22.0), (27.0, -95.0, 22.0), (27.0, -100.5, 22.0), (27.0, -100.5, 14.0), (27.0, -106.0, 9.0), (28.0, (hb.ymin + hb.ymax) / 2, HUB_Z + 3)], 4.0))   # bulkhead rear -> lane over the board front strips at z 30 under the main lid, z 22 under the low terrace (inner top 27) -> down beside board B to the hub
for n in ("B", "A1", "A2"):
    X, Y = W(n, -17.0974, 55.7412)
    usbc.append(tube([(hb.xmax - 4, hb.ymax + 1, HUB_Z + 3), (hb.xmax + 2, -99.0, 7.8), (X, -99.0, 7.8), (X, -97.5, Z_TOP + 1.6)], 4.0))   # run at z 9.5, over the B J6 ribbon
addp("wire-ribbons", Compound(wires), (0.85, 0.75, 0.1), "harness to X1/X2 as flat taped ribbons (A1/A2 J3 pads, B J6 pads, B T5-T8 lugs, input boards J2); ASSUMED routing")
addp("usb-cables", Compound(usbc), (0.2, 0.2, 0.6), "USB-C cables bulkhead -> hub -> 3 boards (USB-C at the board front edges), ASSUMED routing; plugs not modelled")
ties = [box(x - 4, x + 4, -107.0 - 4, -107.0 + 4, 0.0, 2.5) for x in (60.0, 140.0)]
addp("tie-points", Compound(ties), (0.3, 0.3, 0.33), "cable-tie anchor pads on the sink field (k1a), ASSUMED")

# ---------------- lid (MJF PA12): Grok b form, front turrets for X1/X2/USB ----------------
w = P["wall"]; dr = P["draft_deg"]; R = P["corner_r"]; TX1 = 62.0
zs, si = P["shoulder_z"], P["shoulder_in"]
outer = dblock(LX0, LX1, LY0, LY1, 0.0, zs + 0.01, r=R)
outer = outer.fuse(dblock(LX0 + si, TX1 + 10, LY0 + si, LY1 - si, zs, P["terrace_top"], r=R - si, draft=dr, tf=4))
outer = outer.fuse(dblock(TX1 - 8, LX1 - si, LY0 + si, LY1 - si, zs, P["main_top"], r=R - si, draft=dr, tf=12))
inner = dblock(LX0 + w, LX1 - w, LY0 + w, LY1 - w, -1.0, zs + 0.02, r=R - w)
inner = inner.fuse(dblock(LX0 + si + w, TX1 + 10 - w, LY0 + si + w, LY1 - si - w, zs, P["terrace_top"] - w, r=R - si - w, draft=dr, tf=1))
inner = inner.fuse(dblock(TX1 - 8 + w, LX1 - si - w, LY0 + si + w, LY1 - si - w, zs, P["main_top"] - w, r=R - si - w, draft=dr, tf=9))
# horizontal turrets (Grok's X1/X2 turrets turned to point south): drafted round bosses, flat front face on the skirt plane
TURRETS = [(CONN["X1"], TZ, P["turret_d"]), (CONN["X2"], TZ, P["turret_d"]), (USB_X, P["usb_z"], P["usb_turret_d"])]
for (X, Zc, d) in TURRETS:
    t = extrude(Plane(origin=(X, LY0, Zc), z_dir=(0, 1, 0)) * Circle(d / 2), amount=P["turret_len"], taper=-3).solid()
    t = t.fillet(3.0, t.faces().sort_by(Axis.Y)[0].edges())
    t = isect(t, box(LX0, LX1, LY0, LY1, 0.0, P["main_top"]))
    outer = outer.fuse(t)
    inner = inner.fuse(isect(cyl(min(P["turret_bore"], d - 2 * w - 2), (X, WALL_IN, Zc), P["turret_len"] + 10, (0, 1, 0)), box(LX0, LX1, LY0, LY1, 0.2, 200)))
for k, (X, Y) in FEED.items():
    outer = outer.fuse(dround(X, Y, 26.0, 20.0, P["collar_top"], draft=10, tf=1.5))
lid = outer.cut(inner)
for k, (X, Y) in FEED.items(): lid = lid.cut(cyl(16.0, (X, Y, 10), 40))          # AF13 hex across corners 15.0
# OUT1-4 bay: open well over the G10 carrier (its top is the bay floor, lugs in its pockets); wire-way from the well to the west lid edge
wl = dblock(CX0 - 0.6, CX1 + 0.6, CY0 - 0.6, CY1 + 0.6, ZCL - 2.0, P["terrace_top"] + 5, r=3.5)
liner = dblock(CX0 - 0.6 - w, CX1 + 0.6 + w, CY0 - 0.6 - w, CY1 + 0.6 + w, max(ZCL - 2.0, ZB1 + 0.3), P["terrace_top"] - 0.5, r=3.5 + w)   # stays above the copper bars
lid = lid.fuse(liner).cut(wl)
wy0, wy1 = P["wireway_y0"], P["wireway_y1"]; wff = Z_L - 0.5                          # wire-way floor 0.5 under the low-tier lug barrels
ww_liner = box(LX0 + 0.5, CX0 - 0.6, wy0 - w, wy1 + w, wff - w, P["terrace_top"] - 0.5)
lid = lid.fuse(ww_liner.cut(box(LX0 - 5, CX0 + 2, wy0, wy1, wff, 200)))
lid = lid.cut(box(LX0 - 5, CX0 + 2.0, wy0, wy1, wff, P["terrace_top"] + 20))
# panel cut-outs per TE spec 0425-021-0000 (shell 24): D-hole A 43.08, B 41.45 (flat 19.91 below centre, matching the thread flat in the TE models)
DFLAT = {}
for k, X in CONN.items():
    # flat position taken from each TE model's thread inside the wall slab (HD34 thread reaches lower than the HDP24 flat): + 0.2 clearance
    cm = x1 if k == "X1" else x2
    zlow = bbx(isect(cm, box(X - 30, X + 30, LY0, WALL_IN, TZ - 30, TZ))).zmin
    fl = min(43.08 / 2, max(41.45 - 43.08 / 2, TZ - zlow + 0.2)); DFLAT[k] = round(fl, 2)
    dh = cyl(43.08, (X, LY0 - 1, TZ), w + 2, (0, 1, 0)).cut(box(X - 30, X + 30, LY0 - 2, LY0 + w + 2, TZ - 40, TZ - fl))
    lid = lid.cut(dh)
uh = cyl(20.8, (USB_X, LY0 - 1, P["usb_z"]), w + 2, (0, 1, 0)).cut(box(USB_X - 15, USB_X + 15, LY0 - 2, LY0 + w + 2, P["usb_z"] + 19.4 - 10.4, P["usb_z"] + 15))
lid = lid.cut(uh)
# knuckle ribs on the skirt (Grok), front ribs skipped where a turret sits
for i in range(6):
    X = LX0 + 40 + i * (LX1 - LX0 - 80) / 5
    for side, (Y0_, Y1_) in (("S", (LY0 - 2.0, LY0 + 2.0)), ("N", (LY1 - 2.0, LY1 + 2.0))):
        if side == "S" and any(abs(X - tx) < d / 2 + 6 for (tx, _, d) in TURRETS): continue
        lid = lid.fuse(dblock(X - 5, X + 5, Y0_, Y1_, 0.0, 16.0, r=1.5, tf=1.5))
for i in range(7):                                                          # Grok's top grooves, kept on the north half of the main top
    X = 120 + i * 18.0
    lid = lid.cut(dblock(X - 2, X + 2, LY1 - 54, LY1 - 24, P["main_top"] - 1.2, P["main_top"] + 5, r=1.9))
for (X, Y) in LID_SCREWS:
    lid = lid.fuse(isect(cyl(9.0, (X, Y, 0), 11.0), dblock(LX0, LX1, LY0, LY1, 0, 11, r=R)))   # 11 tall: insert 8.1 + 2.4, clear of the USB flange (z 11.3)
for (X, Y) in LID_SCREWS:
    lid = lid.cut(cyl(5.6, (X, Y, -0.5), 10.5))
    scr.append(("SSH-M4-0.7 x 12", shcs("M4", 12.0, (X, Y, -pt + 4.0), down=False)))
addp("lid", lid, (0.18, 0.18, 0.2), "MJF PA12 lid (Grok b form): walls 3.0, draft 6; front turrets for X1/X2/USB-C; heat-set M4 inserts")
ins = [cyl(5.6, (X, Y, 0.5), 8.1).cut(cyl(4.0, (X, Y, 0.4), 8.3)) for (X, Y) in LID_SCREWS]
addp("heat-set-inserts-M4", Compound(ins), (0.8, 0.65, 0.25), "M4 heat-set insert envelope dia 5.6 x 8.1 (PN TBD, e.g. Ruthex M4x8.1)")

from collections import defaultdict
g = defaultdict(list)
for pn, s in scr: g[pn].append(s)
for pn, ss in g.items(): addp("screws " + pn, Compound(ss), (0.35, 0.35, 0.38), f"{pn} (screw-tool ISO 4762 dims where SSH), qty {len(ss)}")

# ---------------- export ----------------
kids = []
for nm, d in parts.items():
    s = d["shape"]; s.label = nm.replace(" ", "_"); s.color = Color(*d["color"]); kids.append(s)
    export_brep(s, os.path.join(OUT, "brep", nm.replace(" ", "_") + ".brep"))
    if d["step"] and not nm.startswith("vendor"): export_step(s, os.path.join(OUT, "parts", nm.replace(" ", "_") + ".step"))
export_step(Compound(children=kids, label=f"custom-pdm-enclosure-v2b-{VAR}"), os.path.join(OUT, f"custom-pdm-enclosure-v2b-{VAR}-assembly.step"))
export_step(Compound(children=[k for k in kids if not k.label.startswith(("board", "input-board"))], label="noboards"), os.path.join(OUT, f"v2b-{VAR}-noboards.step"))
bb = bbx(Compound([d["shape"] for nm, d in parts.items() if not nm.startswith("vendor-plug")]))
lb = bbx(parts["lid"]["shape"]); sb = bbx(parts["heat-sink"]["shape"])
meta = dict(variant=VAR, P=P, Z_BOT=Z_BOT, Z_TOP=Z_TOP, X0=X0, M6TOP=M6TOP, TTOP=TTOP, M6_EXT_TOP=M6_EXT_TOP, M4_EXT_TOP=M4_EXT_TOP, OUT_SEAT=SEAT, OUT_LUGANG=LUGANG, CARRIER=dict(x=(CX0, CXM, CX1), y=(CY0, CY1), z=(Z_CB, ZCL, ZCU), anchors=ANCH),
            footprint=(LX0, LX1, LY0, LY1), lid_bbox=(lb.xmin, lb.xmax, lb.ymin, lb.ymax, lb.zmin, lb.zmax),
            sink_bbox=(sb.xmin, sb.xmax, sb.ymin, sb.ymax, sb.zmin, sb.zmax), overall_no_plugs=(bb.xmin, bb.xmax, bb.ymin, bb.ymax, bb.zmin, bb.zmax),
            CONN=CONN, USB_X=USB_X, FEED=FEED, OUTT=OUTT, T58=T58, fan=fan_info, feet=FEET, lid_screws=LID_SCREWS,
            stripped=dict(A_J3=dA, B_J6=dB), d_flat_below_centre=DFLAT, hub_bbox=[hb.xmin, hb.xmax, hb.ymin, hb.ymax], standoffs=[(n, h) for n, h, _ in SO],
            labels={k: d["label"] for k, d in parts.items()}, colors={k: d["color"] for k, d in parts.items()},
            screws={pn: len(ss) for pn, ss in g.items()}, n_fins=len(fins))
json.dump(meta, open(os.path.join(OUT, "meta.json"), "w"), indent=1, default=str)
print("done", VAR, len(parts), "overall(no plugs)", [round(v, 1) for v in meta["overall_no_plugs"]], "stripped", dA, dB)
