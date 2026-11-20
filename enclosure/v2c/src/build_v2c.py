"""custom-pdm enclosure v2c - v2b rebuilt from our own sources, with the OUT1-4 riser clearance fix.
build123d (handbuilt-cad CAD venv, DansPC WSL). Usage: python build_v2c.py F1|F2   (run through run.sh)
  F1 = 2 x 30 mm Sunon fans embedded in the heat-sink envelope (fan bay at the east end, push west)  <- the pick (b2a)
  F2 = one Noctua NF-A6x15 blowing UP into a machined pocket in the fin field, swept radial fins (needs the Noctua STEP)
Inputs (no outside pack; Dan 2026-11-16 "you designed it"):
  BOARDS = board STEPs exported from this repo's KiCad boards by export_boards.ps1 (board-A / board-B / input-board.step)
  VENDOR = maker CAD downloaded per enclosure/v2c/vendor/README.md (licence-restricted: git-ignored)
  Both default (run.sh) to <repo root>/.claude/cache/enclosure/{boards,vendor}: git-ignored and outside every worktree.
World frame (unchanged since Grok TEST 2 / v2b): X east, Y north, Z up, Z=0 = heat-sink field, board north edges at Y=0. mm.
Changes vs v2b (geometry is v2b's except these):
  - OUT1-4 riser seats 8.5 mm from the terminal centre for all four (v2b: OUT2/OUT4 7.52, OUT1/OUT3 8.19): the M4 foot-screw
    head (dk 7.0) now clears the seat column by 1.0 mm, 0.5 mm with the modelled R0.5 column-root fillet (cutter corner radius)
  - board STEPs from our KiCad (main), no J3 / J6 bodies to strip (they are wire pads in the boards now); input-board J2
    = Molex 43045-1200 maker STEP (the KiCad 10 library has no Micro-Fit model)
  - TE panel nut 2411-001-2405 and lock washer 2414-001-2486 from TE's CAD (v2b: nut drawn, 6 mm assumed, no washer)
  - fan screws M3 x 12 horizontal into the fan wall (v2b drew M3 x 16 vertical); lid-screw counterbores dia 8.0 (DIN 974-1
    for M4 SHCS; v2b 7.5 left 0.25 mm round the head)
  - every part is its own STEP file named by its part number (product name = PN, description = what + material + rev) and
    the assembly STEP references those files (external references, one instance per placement) (Dan 2026-11-16)
Rev C (2026-11-20, job cadfetch): the last three drawn stand-ins replaced by maker CAD: Sunon MF30101V1 fan (DigiKey
  "Manufacturer Provided" STEP, 10.4 thick: fan-screw heads 0.4 further east), Phoenix 3240083 ring lug (phoenixcontact.com STEP:
  ring centre to barrel end 14, barrel OD 5.6; OUT1-4 wire ends follow), Amphenol LTW UC-00PMFY-SC7001 (amphenolltw.com STEP:
  round flange, nut moved out by the wall, FPC tail 47 to a Y-beam contact; the USB cable now starts at the tail end)
ASSUMED = designer's choice, TBD = not confirmed by a primary source.
"""
import os, sys, json, math
from build123d import *
from OCP.gp import gp_Trsf, gp_Vec
VAR = sys.argv[1] if len(sys.argv) > 1 else "F1"
REV = "v2c"
BOARDS = os.environ["BOARDS"]; VENDOR = os.environ["VENDOR"]
OUT = os.path.join(os.environ.get("RUN_DIR", "/tmp/v2c"), VAR)
import shutil
for _d in ("parts", "brep"):                                         # clear stale outputs so the checks see only this build
    shutil.rmtree(os.path.join(OUT, _d), ignore_errors=True); os.makedirs(os.path.join(OUT, _d), exist_ok=True)
from screwtool_twin import shcs, standoff_mf, row as screw_row
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
IDENT = Location()
def L(x=0.0, y=0.0, z=0.0, rx=0.0, ry=0.0, rz=0.0): return Location((x, y, z), (rx, ry, rz))

# ---------------- part catalogue + placements (every part = its own file; Dan 2026-11-16) ----------------
from OCP.TopLoc import TopLoc_Location
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from build123d.topology import Shape
def bake(s):
    """part shapes carry no TopLoc (a located shape becomes an un-named, inline sub-product in the XCAF STEP writer):
    an identity location is dropped, a real one is baked into the geometry"""
    loc = s.wrapped.Location()
    if loc.IsIdentity(): return Shape.cast(s.wrapped.Located(TopLoc_Location()))
    return Shape.cast(BRepBuilderAPI_Transform(s.wrapped.Located(TopLoc_Location()), loc.Transformation(), True).Shape())
CAT = {}     # pn -> dict(shape (part's own frame), name, maker, desc, material, kind, source)
ITEMS = {}   # item (BREP / render name) -> dict(pn, locs, color)
def part(pn, shape, name, desc, material, kind, maker="custom-pdm", source=""):
    """kind: made | bought | bought-drawn (no maker CAD reachable: modelled from the maker's drawing) | board | harness"""
    if pn in CAT: return pn
    CAT[pn] = dict(shape=bake(shape), name=name, maker=maker, desc=desc, material=material, kind=kind, source=source)
    return pn
def item(nm, pn, locs, color):
    ITEMS[nm] = dict(pn=pn, locs=list(locs), color=color)
def made(nm, pn, shape, color, name, desc, material, kind="made"):
    """a part built in the world frame (one instance, identity placement)"""
    part(pn, one(shape) if kind == "made" else shape, name, desc, material, kind); item(nm, pn, [IDENT], color)
def world(nm):
    it = ITEMS[nm]; s = CAT[it["pn"]]["shape"]
    if it["locs"] == [IDENT]: return s
    return Compound([s.moved(l) for l in it["locs"]])
SCREWS = []  # (size, L, Location) for the head-clearance check
SCR = {}     # pn -> [locs]
def screw(size, Lg, loc):
    pn = f"ISO4762-{size}x{Lg:g}"
    part(pn, shcs(size, Lg, (0, 0, 0)), f"Socket head cap screw ISO 4762 {size} x {Lg:g}",
         "screw-tool ISO 4762 dims (head-seat origin), cosmetic thread", "steel class 8.8 zinc plated (ASSUMED grade)", "bought", maker="ISO 4762")
    SCR.setdefault(pn, []).append(loc); SCREWS.append((size, Lg, loc))

# ---------------- driving dimensions ----------------
P = dict(
    gap_boards=2.0, ped_h=3.0, pad_t=1.0, plate_t=8.0,
    fin_h=30.0, fin_t=2.0, fin_pitch=6.0, fin_edge=10.0,      # Grok's straight fins (F1)
    foot_h=10.0, foot_af=24.0, foot_web_t=4.0, foot_web_L=20.0,  # reinforced feet: hex AF24, 2 webs each, 10 below fin tips
    wall=3.0, edge_clear=10.0,
    lid_y0=-130.0,           # front (south) outer face of the skirt (v2b)
    terrace_top=30.0, collar_top=38.23,
    main_top=66.0,
    turret_d=62.0, turret_z=33.0, turret_bore=54.0, turret_len=24.0,
    usb_turret_d=46.0, usb_z=30.0,
    deck_t=3.0, in_boss=4.0, so_m3_len=25.0,
    bar_t=5.0, batt_w=20.0, batt_yc=-63.5, gnd_w=15.0, gnd_yc=-5.0,   # copper bars (C110) 20x5 / 15x5
    boss6_af=13.0, boss4_d=9.5, boss4_flats=8.0, lug_t=2.0,
    bay_floor_top=19.2,
    out_lug_t=1.0, out_lug_w=8.0, out_lug_L=14.0, out_barrel_d=5.6, out_barrel_L=6.0, out_wire_d=4.2,   # Phoenix 3240083 C-RC 6/M4 DIN: re-measured from the maker STEP in ring_lug_local() (revC; revB drew L 17.5 / barrel 6.0 from catalogue dims); 10 AWG GXL OD 4.2 ASSUMED
    out_seat_lo=19.0, out_seat_hi=29.0,                       # OUT1-4 lug seat tops: west pair low tier, east pair high tier (d1a / e1a)
    riser_r=4.0, riser_foot=4.0, pocket_d=5.0, ear_t=5.0, riser_d=8.5, riser_root_r=0.5, riser_foot_r=3.75,   # v2c: foot arm R3.75 (v2b R4): G10 web between neighbouring key slots 1.8 (was 1.3 < 1.52 composite minimum)   # v2c: seat 8.5 from the T centre (all four), R0.5 column-root fillet
    wireway_y0=-47.2, wireway_y1=-19.3,
    corner_r=14.0, draft_deg=6.0, shoulder_z=10.0, shoulder_in=2.0,
    ribbon_w=28.0, ribbon_t=4.0,
    lid_cb_d=8.0,            # v2c: M4 counterbore DIN 974-1 (v2b 7.5)
    nut_washer_t=2.28,       # TE 2414-001-2486 lock washer thickness (TE CAD: 2.28)
)
Z_BOT = P["ped_h"] + P["pad_t"]; T_PCB = 1.769872; Z_TOP = Z_BOT + T_PCB
X0 = {"B": 0.0}; X0["A1"] = 111.39 + P["gap_boards"]; X0["A2"] = X0["A1"] + 72.39 + P["gap_boards"]
def W(n, xk, yk): return (X0[n] + xk + 37.846, -(yk + 33.274))

# ---------------- boards (own STEP files from our KiCad, export_boards.ps1) ----------------
stepA = import_step(os.path.join(BOARDS, "board-A.step"))
stepB = import_step(os.path.join(BOARDS, "board-B.step"))
stepI = import_step(os.path.join(BOARDS, "input-board.step"))
def tall_near(s, cx0, cy0, rxy, zmin_keep):
    """v2b stripped the J3 DT15 / J6 Micro-Fit bodies from Grok's board STEPs; our boards have wire pads there (a1a / a2b),
    so nothing may stand there now: count what would have been stripped (expect 0)"""
    n = 0
    for so in s.solids():
        b = bbx(so); cx, cy = (b.xmin + b.xmax) / 2, (b.ymin + b.ymax) / 2
        if abs(cx - cx0) < rxy and abs(cy - cy0) < rxy and (b.zmax > zmin_keep or b.zmin < -0.5) and b.xlen < 70: n += 1
    return n
dA, dB = tall_near(stepA, 0.0, 0.0, 16.0, 6.0), tall_near(stepB, -1.5, 1.5, 4.5, 3.0)
part("CPDM-PCB-A", stepA, "Main board A (8 x 7.5 A outputs + inputs)", "dingoPDM v7.5 derived, J3 as wire pads (a1a); KiCad hardware/board-a, STEP by export_boards.ps1",
     "FR4 4-layer PCB assembly", "board", source="hardware/board-a/DingoPDM.kicad_pcb")
part("CPDM-PCB-B", stepB, "Main board B (4 x 31 A + 4 x 15 A outputs)", "dingoPDM-Max derived, J6 as wire pads (a2b); KiCad hardware/board-b-max, STEP by export_boards.ps1",
     "FR4 4-layer PCB assembly", "board", source="hardware/board-b-max/dingoPDM-Max.kicad_pcb")
part("CPDM-PCB-IN", stepI, "Input board (8 inputs)", "KiCad hardware/input-board, STEP by export_boards.ps1; J2 Molex 43045-1200 placed as its own part",
     "FR4 PCB assembly", "board", source="hardware/input-board/input-board.kicad_pcb")
item("board-B", "CPDM-PCB-B", [L(X0["B"] + 37.846, -33.274, Z_BOT)], (0.1, 0.45, 0.15))
item("board-A1", "CPDM-PCB-A", [L(X0["A1"] + 37.846, -33.274, Z_BOT)], (0.1, 0.45, 0.15))
item("board-A2", "CPDM-PCB-A", [L(X0["A2"] + 37.846, -33.274, Z_BOT)], (0.1, 0.45, 0.15))
IN_X = {"IN3": 64.0, "IN1": 130.0, "IN2": 196.0}; IN_Y_N = -14.6               # Grok b input-board placement, unchanged
z_deck_bot = Z_TOP + P["so_m3_len"]; z_deck_top = z_deck_bot + P["deck_t"]; Z_IN = z_deck_top + P["in_boss"]
def in_hole(n, hx, hy): return (IN_X[n] + hy, IN_Y_N - 66.0 + hx)
for n, x in IN_X.items():
    item(f"input-board-{n}", "CPDM-PCB-IN", [L(x, IN_Y_N - 66.0, Z_IN, rz=90)], (0.1, 0.35, 0.55))
# input-board J2 = Molex 43045-1200 (maker STEP). Footprint at (10, 24) rot 90 on the input board (KiCad, pads 1-6 at local
# y 0, 7-12 at y 3, pitch 3 along x). Molex model: Y up from the board, +Z toward the mating face, pin rows at Z -8.92 / -11.92,
# pins at X -7.5..7.5 -> footprint 3-D frame (x, y up-screen, z up): (7.5 - X, Z + 8.92, Y); then rot 90 about z to (10, -24).
_t = gp_Trsf(); _t.SetValues(-1, 0, 0, 7.5, 0, 0, 1, 8.92, 0, 1, 0, 0)
M_MOLEX = L(10.0, -24.0, 1.51, rz=90) * Location(_t)
molex = import_step(os.path.join(VENDOR, "Molex_43045-1200", "430451200.stp"))
part("43045-1200", molex, "Molex Micro-Fit 3.0 header 2x6 right angle (input board J2)", "Molex 43045-1200, fitted on the input board by the PCB assembler",
     "PA (UL94V-0), tin contacts", "bought", maker="Molex", source="molex.com part 430451200, STEP AP242")
item("vendor-J2-Molex-43045-1200", "43045-1200", [L(x, IN_Y_N - 66.0, Z_IN, rz=90) * M_MOLEX for x in IN_X.values()], (0.15, 0.15, 0.15))

# ---------------- footprint ----------------
ec = P["edge_clear"]
LX0 = -ec; LX1 = X0["A2"] + 72.39 + ec; LY1 = ec; LY0 = P["lid_y0"]
pt = P["plate_t"]; zf0 = -pt - P["fin_h"]; zfoot = zf0 - P["foot_h"]
def box(x0, x1, y0, y1, z0, z1):
    x0, x1 = sorted((x0, x1)); y0, y1 = sorted((y0, y1)); z0, z1 = sorted((z0, z1))
    return Solid.make_box(x1 - x0, y1 - y0, z1 - z0, Plane(origin=(x0, y0, z0)))
def cyl(d, p0, Lc, axis=(0, 0, 1)):
    return Solid.make_cylinder(d / 2, Lc, Plane(origin=p0, z_dir=axis))
def hexp(af, p0, Lh, axis=(0, 0, 1), rot=30.0):
    return extrude(Plane(origin=p0, z_dir=axis) * Rot(0, 0, rot) * RegularPolygon(af / 2 / math.cos(math.pi / 6), 6), amount=Lh).solid()
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
        a, b = Vector(*a), Vector(*b); Lt = (b - a).length
        c = Solid.make_cylinder(d / 2, Lt, Plane(origin=a, z_dir=(b - a).normalized())).fuse(Solid.make_sphere(d / 2).translate(b))
        s = c if s is None else s.fuse(c)
    return s.fuse(Solid.make_sphere(d / 2).translate(Vector(*pts[0])))
def ribbon(pts, w, t):
    """flat taped wire ribbon (width w horizontal, thickness t) through pts: chain of oriented boxes"""
    s = None
    for a, b in zip(pts[:-1], pts[1:]):
        a, b = Vector(*a), Vector(*b); d = b - a; Lr = d.length
        side = Vector(0, 0, 1).cross(d.normalized())
        if side.length < 1e-6: side = Vector(1, 0, 0)
        side = side.normalized(); up = d.normalized().cross(side)
        pl = Plane(origin=a - side * (w / 2) - up * (t / 2), x_dir=side, z_dir=d.normalized())
        seg = Solid.make_box(w, t, Lr + t, Plane(origin=pl.origin, x_dir=side, z_dir=d.normalized())).translate(-d.normalized() * (t / 2))
        s = seg if s is None else s.fuse(seg)
    return s
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
    # Grok's straight east-west fins, stopped at a fan bay at the east end; 2 x Sunon 30x30x10 inside the outline, push west
    bay_x0 = LX1 - fe - 18.0
    fins = []
    y = LY0 + fe
    while y + P["fin_t"] <= LY1 - fe + 1e-6:
        fins.append(box(LX0 + fe + 16, bay_x0 + 1.0, y, y + P["fin_t"], zf0, -pt)); y += P["fin_pitch"]   # v2c: fins run into the fan wall (v2b left a 1 mm slot, narrower than any cutter)
    finf = Compound(fins)
    fan_y = [(LY0 + LY1) / 2 - 16, (LY0 + LY1) / 2 + 16]
    fan_z = zf0 + 14.5   # v2c: 0.5 lower than v2b, so the upper M3 fan-screw heads (dk 5.5 at +12) clear the plate underside by 0.75 (head rule; was 0.25)
    wall_x = bay_x0 + 1.0                                         # 3 mm fan wall (part of the sink), fans bolt to its east face
    fwall = box(wall_x, wall_x + 3.0, LY0 + fe + 8, LY1 - fe - 8, zf0, -pt)
    for fy in fan_y: fwall = fwall.cut(cyl(28.0, (wall_x - 1, fy, fan_z), 5.0, (1, 0, 0))).cut(box(wall_x - 1, wall_x + 4, fy - 6, fy + 6, zf0 - 1, fan_z - 13))   # v2c: 12 wide notch from the fin tips into the hole (v2b left a 0.5 / 1.0 bridge under it); the screw corners keep >= 1.25
    for fy in fan_y:
        for dy in (-12, 12):
            for dz in (-12, 12): fwall = fwall.cut(cyl(2.5, (wall_x - 1, fy + dy, fan_z + dz), 5.0, (1, 0, 0)))   # M3 tap (Sunon hole pitch 24)
    finf = finf.fuse(fwall)
    fan_info = dict(kind="2 x Sunon MF30101V1-1000U-A99", x=(wall_x + 3.0, wall_x + 13.0), y=fan_y, z=fan_z)
else:
    FCX, FCY = 150.0, -52.0
    ft = 2.5; r0 = 31.0
    xs0, xs1, ys0, ys1 = LX0 + fe, LX1 - fe, LY0 + fe, LY1 - fe
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
        c = Spline(*[Vector(x, y, -pt) for (x, y) in pts])
        w2 = Wire([c]).offset_2d(ft / 2, kind=Kind.ARC, side=Side.BOTH, closed=False)
        sol = Solid.extrude(Face(w2), Vector(0, 0, zf0 + pt))
        try:
            sol = sol.fillet(1.0, sol.faces().sort_by(Axis.Z)[0].edges())
        except Exception:
            pass
        return sol
    N = 24; fin_len = 0.0
    for i in range(N):
        p = spiral_dense(2 * math.pi * i / N, r0)
        if len(p) > 3: fins.append(fin_from(p)); fin_len += sum(math.dist(a_, b_) for a_, b_ in zip(p[:-1], p[1:]))
        p = spiral_dense(2 * math.pi * (i + 0.5) / N, 62.0)
        if len(p) > 3: fins.append(fin_from(p)); fin_len += sum(math.dist(a_, b_) for a_, b_ in zip(p[:-1], p[1:]))
    fan_info["fin_len_total_mm"] = round(fin_len, 1); fan_info["fin_t"] = ft; fan_info["N"] = N
    psi = math.atan(0.55)
    fan_info["min_channel_mm"] = round(min(r0 * 2 * math.pi / N * math.cos(psi), 62.0 * math.pi / N * math.cos(psi)) - ft, 2)
    finf = Compound(fins)
    pocket = dblock(FCX - 31.5, FCX + 31.5, FCY - 31.5, FCY + 31.5, zf0 - 1, zf0 + 18.0, r=4.0)
    fan_info.update(kind="1 x Noctua NF-A6x15 PWM", c=(FCX, FCY), z_bottom=zf0 + 2.0, z_top=zf0 + 18.0)
finf = finf.cut(*foot_keepout) if foot_keepout else finf
sink = sink.fuse(finf, feet)
if VAR == "F2":
    sink = sink.cut(pocket)
    for dx in (-25, 25):
        for dy in (-25, 25):
            sink = sink.fuse(cyl(8.0, (FCX + dx, FCY + dy, zf0 + 18.0), -pt - zf0 - 18.0))
            sink = sink.cut(cyl(2.5, (FCX + dx, FCY + dy, zf0 + 17.9), 8.0))
    z_apex = fan_info["z_top"] + 1.5; Hc = -pt - z_apex; Rc = 29.0; rt = 1.0
    prof = [(Rc - (Rc - rt) * math.cos(ph), z_apex + Hc * math.sin(ph)) for ph in [math.pi / 2 * i / 24 for i in range(25)]]
    sp = Spline(*[Vector(FCX + r_, FCY, z_) for (r_, z_) in prof])
    wr = Wire([Line((FCX, FCY, z_apex), (FCX + rt, FCY, z_apex)), sp,
               Line((FCX + Rc, FCY, -pt), (FCX, FCY, -pt)), Line((FCX, FCY, -pt), (FCX, FCY, z_apex))])
    cone = revolve(Face(wr), Axis((FCX, FCY, 0), (0, 0, 1)), 360).solid()
    try:
        cone = cone.fillet(0.9, cone.faces().sort_by(Axis.Z)[0].edges())
    except Exception:
        pass
    cone = cone.cut(cyl(4.0, (FCX, FCY, -pt - 4.2), 4.3))
    sink = sink.cut(cyl(3.4, (FCX, FCY, -pt - 0.1), pt + 0.2))
    sink = sink.cut(Solid.make_cone(3.4 / 2, 6.6 / 2, 1.6, Plane(origin=(FCX, FCY, -1.6))))
    flow_cone = cone
    fan_info.update(cone=dict(profile="reverse velocity stack, quarter-ellipse concave flare", R=Rc, tip_r=rt, H=round(Hc, 2), apex_gap=1.5, z_apex=round(z_apex, 2)))
for (X, Y, sx, sy) in FEET:
    sink = sink.cut(cyl(6.6, (X, Y, zfoot - 1), -zfoot + 2))           # M6 clearance, bolt-through mounting
LID_SCREWS = []
nx = 5
for i in range(nx):
    X = LX0 + 30 + i * (LX1 - LX0 - 60) / (nx - 1); LID_SCREWS += [(X, LY1 - 5.0)]
LID_SCREWS += [(X, LY0 + 5.0) for X in (20.0, 66.0, 147.0, 222.0, LX1 - 20.0)]
LID_SCREWS += [(LX0 + 5.0, (LY0 + LY1) / 2), (LX1 - 5.0, (LY0 + LY1) / 2)]
for (X, Y) in LID_SCREWS:
    sink = sink.cut(cyl(4.5, (X, Y, -pt - 1), pt + 2)); sink = sink.cut(cyl(P["lid_cb_d"], (X, Y, -pt - 1), 5.0))   # counterbore to Z -4
made("heat-sink", f"CPDM-ENC-101-{VAR}", sink, (0.72, 0.72, 0.76), f"Heat sink / base {VAR}",
     "one-piece 3-axis machined base: plate 8, fins, pedestals, tapped bosses, reinforced hex feet", "6061-T6 aluminium")
if VAR == "F2":
    made("flow-cone-PA12", "CPDM-ENC-111", flow_cone, (0.22, 0.22, 0.25), "Flow cone (F2)", "reverse-velocity-stack flare, M3 heat-set insert", "MJF PA12")
    screw_csk = Solid.make_cone(1.5, 3.0, 1.5, Plane(origin=(0, 0, -1.5))).fuse(cyl(3.0, (0, 0, -12.0), 10.5))
    part("ISO10642-M3x12", screw_csk, "Countersunk socket screw ISO 10642 M3 x 12", "envelope", "steel 8.8 zinc (ASSUMED)", "bought", maker="ISO 10642")
    item("screws_CSK-M3-0.5_x_12_(ISO_10642)", "ISO10642-M3x12", [L(FCX, FCY, 0)], (0.35, 0.35, 0.38))
made("gap-pads", "CPDM-ENC-110", Compound(pads), (0.95, 0.5, 0.6), "Gap pads (9 pieces, pedestal outlines)",
     "1.0 mm insulating gap pad, k >= 3 W/mK (b3a), cut to the pedestal outlines; product TBD", "silicone gap pad, k >= 3 W/mK", kind="made-set")

# ---------------- vendor models ----------------
def vstep(rel): return import_step(os.path.join(VENDOR, rel))
if VAR == "F1":
    # Sunon MF30101V1-1000U-A99: maker STEP (DigiKey models/10441405 "Manufacturer Provided", Sunon Creo export
    # MF3010_K201004120G, DigiKey CAD model agreement accepted 2026-11-20). It is a solid envelope (frame outline, 4 x dia 3.2
    # through holes at 24 pitch, no bore / blades): fit only, not for flow. Maker frame: axis +y, faces y 0 / 10.4, centre
    # x = z = 0. Part frame (unchanged): face at x 0 on the fan wall, axis +x, centre (0, 0, 0): maker y -> x, x -> -y.
    f = vstep("Sunon_MF30101V1-1000U-A99/Sunon_MF30101V1-1000U-A99_259_Doc-0175505-7-0.stp")
    f = f.moved(Plane(origin=(0, 0, 0), x_dir=(0, -1, 0), z_dir=(0, 0, 1)).location)
    fb = bbx(f); assert abs(fb.ylen - 30) < 0.05 and abs(fb.zlen - 30) < 0.05 and abs(fb.xmin) < 0.01, ("Sunon STEP frame", fb.xmin, fb.ylen, fb.zlen)
    FAN_T = round(fb.xlen, 3)                                       # 10.4 in the maker STEP (spec nominal 10)
    fan_info["x"] = (wall_x + 3.0, wall_x + 3.0 + FAN_T); fan_info["t_maker_step"] = FAN_T
    part("MF30101V1-1000U-A99", f, "Sunon fan 30 x 30 x 10, 12 V", "Sunon maker STEP (solid envelope, no bore / blades; fit only)",
         "PBT frame", "bought", maker="Sunon", source="digikey.com/en/models/10441405 Manufacturer Provided STEP (259_Doc-0175505-7-0.stp)")
    item("fans-Sunon-MF30101V1", "MF30101V1-1000U-A99", [L(fan_info["x"][0], fy, fan_z) for fy in fan_info["y"]], (0.1, 0.1, 0.1))
    for fy in fan_info["y"]:
        for dy in (-12, 12):
            for dz in (-12, 12):
                screw("M3", 12.0, L(fan_info["x"][1], fy + dy, fan_z + dz, ry=90))   # horizontal, head on the fan's east face; maker fan 10.4 thick -> 1.6 mm (3 threads) into the 3 mm wall (was 2.0 with the drawn 10 mm fan); M3 x 14 would poke 0.6 out of the wall into the fins
else:
    nf = vstep("noctua_NF-A6x15/NF-A6x15_Public-CAD.stp")
    b = bbx(nf.rotate(Axis.X, 90))
    part("NF-A6x15-PWM", nf, "Noctua NF-A6x15 PWM fan", "Noctua public CAD (rendering / integration only)", "", "bought", maker="Noctua")
    item("vendor-fan-Noctua-NF-A6x15", "NF-A6x15-PWM",
         [L(fan_info["c"][0] - (b.xmin + b.xmax) / 2, fan_info["c"][1] - (b.ymin + b.ymax) / 2, fan_info["z_bottom"] - b.zmin, rx=90)], (0.55, 0.35, 0.25))
# X1 / X2 receptacles + mating plugs: TE customer view models, axis local +Z = mating face; local Z -> world -Y, local Y -> world Z
TZ = P["turret_z"]; WALL_IN = LY0 + P["wall"]
YOFF = WALL_IN - 26.16                                               # world Y of the connector local z=0 (mating face)
CONN = {"X1": 108.0, "X2": 186.0}; USB_X = 246.0
TE = {"X1": ("HD34-24-21SN", "HD34-24-21SN/c-hd34-24-21sn-p1-3d.stp", "TE DEUTSCH HD30 receptacle, shell 24, 21 way, sockets, panel nut mount (X1, outputs)"),
      "X2": ("HDP24-24-47SE-L017", "HDP24-24-47SE-L017/c-hdp24-24-47se-l017-b-3d.stp", "TE DEUTSCH HDP20 receptacle, shell 24, 47 way, sockets, panel nut mount (X2, signals / CAN)")}
PLUG = {"X1": ("HD36-24-21PN", "HD36-24-21PN/c-hd36-24-21pn-d1-3d.stp", "TE DEUTSCH HD30 plug, shell 24, 21 way, pins (X1 mate; harness side)"),
        "X2": ("HDP26-24-47PE-L015", "HDP26-24-47PE-L015/c-hdp26-24-47pe-l015-c-3d.stp", "TE DEUTSCH HDP20 plug, shell 24, 47 way, pins (X2 mate; harness side)")}
xc = {}
for k, (pn, f, desc) in TE.items():
    s = vstep(f); part(pn, s, desc.split(" (")[0], desc, "thermoplastic shell", "bought", maker="TE Connectivity", source=f"te.com CVM_{pn} STEP")
    loc = L(CONN[k], YOFF, TZ, rx=90); xc[k] = s.moved(loc)
    item(f"vendor-{k}-{pn}", pn, [loc], (0.6, 0.6, 0.62) if k == "X1" else (0.1, 0.1, 0.1))
for k, (pn, f, desc) in PLUG.items():                              # mated position APPROXIMATE (plug +Z end 16 mm in from the mating face)
    s = vstep(f); part(pn, s, desc.split(" (")[0], desc + "; mated position approximate", "thermoplastic shell", "bought", maker="TE Connectivity", source=f"te.com CVM_{pn} STEP")
    b = bbx(s.rotate(Axis.X, -90))
    item(f"vendor-plug-{pn}", pn, [L(CONN[k], YOFF + 16.0 - b.ymax, TZ, rx=-90)], (0.25, 0.25, 0.27))
# panel nut 2411-001-2405 + lock washer 2414-001-2486 (TE spec 0425-021-0000), TE CAD: nut axis z, z -6.35..0; washer axis y, +/-1.14
nut = vstep("2411-001-2405/c-2411-001-2405-h-3d.stp"); wsh = vstep("2414-001-2486/c-2414-001-2486-99-3d.stp")
part("2411-001-2405", nut, "TE panel nut, shell 24", "TE 2411-001-2405 jam nut for HD30 / HDP20 shell 24 receptacles", "aluminium / zinc (TE)", "bought", maker="TE Connectivity", source="te.com CVM_2411-001-2405 STEP")
part("2414-001-2486", wsh, "TE lock washer, shell 24", "TE 2414-001-2486 lock washer, between panel and nut (spec 0425-021-0000)", "steel (TE)", "bought", maker="TE Connectivity", source="te.com CVM_2414-001-2486 STEP")
wt_ = P["nut_washer_t"]
item("panel-washers-2414-001-2486", "2414-001-2486", [L(X, LY0 - wt_ / 2, TZ) for X in CONN.values()], (0.5, 0.5, 0.52))
item("panel-nuts-2411-001-2405", "2411-001-2405", [L(X, LY0 - wt_, TZ, rx=-90) for X in CONN.values()], (0.12, 0.12, 0.12))
# USB-C bulkhead Amphenol LTW UC-00PMFY-SC7001: maker STEP + 2D drawing from amphenolltw.com (product page "Download / CAD",
# (3D STP) UC-00PMFY-SC7001-STP.stp, drawing rev C 2021-05-07). Maker frame: axis +x = mating face at x 22, D-flat of the
# 13/16"-28 UN thread on +y (8.7 from the axis; panel cut-out D 20.8 / flat 19.4), housing flange dia 25 at x 4..6.8, hex nut
# AF 25.4 modelled screwed back onto the flange (x 6.8..10.8, no panel), FPC tail 47 to a 44-pin Y-beam contact at x -46.8.
# The nut is part of the same maker solid: it is cut out (outside the thread OD) and moved out by the wall thickness, so the
# 3 mm wall sits between flange (inside) and nut (outside) as mounted. Part frame (unchanged): axis -y out of the box, wall
# inner face at y 0, flat on +z (lid cut-out), axis at x 0 / z 0: maker x -> -y, y -> +z, z -> -x.
w_ = P["wall"]
ubm = vstep("AmphenolLTW_UC-00PMFY-SC7001/UC-00PMFY-SC7001-STP.stp")
U_FL, U_NUT1 = 6.8, 10.8                                            # maker x: flange front face / nut front face
nut_zone = box(U_FL, U_NUT1 + 0.01, -20, 20, -20, 20).cut(cyl(20.7, (U_FL - 1, 0, 0), U_NUT1 - U_FL + 3, (1, 0, 0)))
u_nut = isect(ubm, nut_zone); u_body = ubm.cut(nut_zone)
assert 600 < u_nut.volume < 1200, ("USB nut split", u_nut.volume)
ub = Compound(list(u_body.solids()) + list(u_nut.moved(Location((w_, 0, 0))).solids()))
ub = ub.moved(Plane(origin=(0, U_FL, 0), x_dir=(0, -1, 0), z_dir=(-1, 0, 0)).location)
U_TAIL = round(bbx(ub).ymax, 3)                                      # FPC Y-beam end, from the wall inner face (53.6)
part("UC-00PMFY-SC7001", ub, "Amphenol LTW USB-C bulkhead, sealed, front fastened, FPC + 44-pin Y-beam",
     "Amphenol LTW maker STEP; panel nut moved out by the 3 mm wall (as mounted); inner end = FPC 47 to a 44-pin Y-beam contact (needs mating PCB pads)",
     "thermoplastic housing, shielded", "bought", maker="Amphenol LTW", source="amphenolltw.com UC-00PMFY-SC7001 (3D STP) + (2D) rev C")
item("usbc-bulkhead-UC-00PMFY-SC7001", "UC-00PMFY-SC7001", [L(USB_X, WALL_IN, P["usb_z"])], (0.15, 0.15, 0.15))
hub = vstep("adafruit_5997_5997-CH334F-4-Port-Hub.step")
b = bbx(hub.rotate(Axis.Z, 90)); HUB_Z = 4.0
part("5997", hub, "Adafruit 5997 CH334F 4-port USB hub", "Adafruit_CAD_Parts STEP (MIT)", "PCB assembly", "bought", maker="Adafruit", source="github.com/adafruit/Adafruit_CAD_Parts")
hub_loc = L(-2.0 - b.xmin, WALL_IN + 7.5 - b.ymin, HUB_Z - b.zmin, rz=90)
item("vendor-hub-Adafruit-5997", "5997", [hub_loc], (0.1, 0.1, 0.4))
hb = bbx(hub.moved(hub_loc))
part("CPDM-BUY-303", cyl(5.0, (0, 0, 0), HUB_Z), "M2.5 x 4 standoff", "M2.5 hex / round standoff 4 mm under the hub, maker PN TBD (buy to spec)", "brass Ni", "bought", maker="(TBD)")
item("hub-standoffs-M2.5x4", "CPDM-BUY-303", [L(x, y, 0.0) for x in (hb.xmin + 2.5, hb.xmax - 2.5) for y in (hb.ymin + 2.5, hb.ymax - 2.5)], (0.3, 0.3, 0.33))

# ---------------- terminals: copper bosses (v3b) on board B J1/J3 and T1-T4; copper bars to A1/A2 ----------------
M6TOP = Z_BOT + max(bbx(so).zmax for so in stepB.solids() if abs(bbx(so).xlen - 10) < 0.6)
TTOP = Z_BOT + 4.73
FEED = {"BATT+": W("B", -24.638, 27.178), "GND": W("B", -30.48, -27.178)}
FEED_A = {n: {"BATT+": W(n, -24.638, 27.178), "GND": W(n, -30.48, -27.178)} for n in ("A1", "A2")}
OUTT = {"OUT1": W("B", 12, 4.75), "OUT3": W("B", 12, -4.75), "OUT2": W("B", -12, 4.75), "OUT4": W("B", -12, -4.75)}
T58 = {f"T{i}": W("B", 68.394, y) for i, y in zip((5, 6, 7, 8), (-23.584, -0.294, 22.996, 46.286))}
ZB0, ZB1 = M6TOP, M6TOP + P["bar_t"]
DX0, DX1 = 62.0, 262.0; DY1, DY0 = IN_Y_N + 4.0, IN_Y_N - 66.0 - 4.0
SO = [(n, h, (X, Y)) for (n, h, (X, Y)) in BOSS if DX0 + 3 < X < DX1 - 3 and DY0 + 3 < Y < DY1 - 3]
ANCH = [W("B", 26.67, -21.59), W("B", 26.67, 21.59)]                 # board B H2, H4 (carrier standoffs)
def bar(points_x, yc, w, end_pts):
    xa, xb = min(points_x) - 8.5, max(points_x) + 10.0
    b_ = dblock(xa, xb, yc - w / 2, yc + w / 2, ZB0, ZB1, r=4.0)
    for (X, Y) in end_pts: b_ = b_.cut(cyl(6.6, (X, Y, ZB0 - 1), P["bar_t"] + 2))   # M6 clearance at each terminal
    for (n, h, (X, Y)) in SO:
        if xa < X < xb and yc - w / 2 - 6 < Y < yc + w / 2 + 6:
            b_ = b_.cut(cyl(11.0, (X, Y, ZB0 - 1), P["bar_t"] + 2))                   # standoff pass-through: 11 dia (insulating sleeve)
    for (X, Y) in ANCH: b_ = b_.cut(cyl(11.0, (X, Y, ZB0 - 1), P["bar_t"] + 2))       # carrier standoff pass-through
    return b_
bp = [FEED["BATT+"], FEED_A["A1"]["BATT+"], FEED_A["A2"]["BATT+"]]
gp = [FEED["GND"], FEED_A["A1"]["GND"], FEED_A["A2"]["GND"]]
made("copper-bar-BATT", "CPDM-ENC-104", bar([p[0] for p in bp], P["batt_yc"], P["batt_w"], bp), (0.85, 0.45, 0.2), "Copper bar BATT+",
     f"{P['batt_w']:g} x {P['bar_t']:g} bar, B J1 -> A1 J1 -> A2 J1; insulating film under, sleeves at standoffs", "C110 copper")
made("copper-bar-GND", "CPDM-ENC-105", bar([p[0] for p in gp], P["gnd_yc"], P["gnd_w"], gp), (0.6, 0.35, 0.2), "Copper bar GND",
     f"{P['gnd_w']:g} x {P['bar_t']:g} bar, B J3 -> A1 J2 -> A2 J2", "C110 copper")
L6 = P["collar_top"] + 1.0 - ZB1                                    # boss top 1 mm above the collar top
bo = hexp(P["boss6_af"], (0, 0, 0), L6).cut(cyl(5.0, (0, 0, L6 - 12), 12.1)).cut(cyl(5.0, (0, 0, -0.1), 10.1))   # M6 tap drill 5.0 both ends
part("CPDM-ENC-106", bo, "Copper terminal boss M6 (BATT+ / GND)", f"hex AF{P['boss6_af']:g} x {L6:.2f}, M6 female both ends, from hex bar", "C110 copper", "made")
item("copper-boss-M6-BATT-GND", "CPDM-ENC-106", [L(X, Y, ZB1) for (X, Y) in FEED.values()], (0.85, 0.5, 0.25))
part("DIN976-M6x19", cyl(6.0, (0, 0, 0), 19.0), "Threaded rod (stud) DIN 976-1 M6 x 19", "stud from the board B M6 terminal into the copper boss", "steel 8.8 zinc (ASSUMED)", "bought", maker="DIN 976-1")
item("screws_M6_stud_19_(threaded_rod)", "DIN976-M6x19", [L(X, Y, M6TOP - 8.0) for (X, Y) in FEED.values()], (0.35, 0.35, 0.38))
for (X, Y) in FEED.values(): screw("M6", 10.0, L(X, Y, ZB1 + L6 + P["lug_t"]))
for n in ("A1", "A2"):
    for (X, Y) in FEED_A[n].values(): screw("M6", 16.0, L(X, Y, ZB1))
# ---- OUT1-4: copper OFFSET RISERS held in ONE G10 carrier (Dan d1a / c1b, e1a 2026-11-13) ----
# Riser = C110 foot arm (R4 x 4 thick) on board B T1-T4 (Wurth REDCUBE 74650074R, M4, max 1.2 N*m) + seat column dia 8.
# v2c: every seat sits P["riser_d"] = 8.5 from its T centre, so the M4 foot-screw head (dk 7.0) clears the column by 1.0
# (0.5 next to the modelled R0.5 column-root fillet = the cutter corner radius); v2b had 7.52 (OUT2 / OUT4) and 8.19.
# Seat directions keep e1a's layout: OUT2 / OUT4 seats moved 1.95 east (x 28.9 -> 30.85), OUT1 / OUT3 0.2 west / 0.3 out.
Z_CB = Z_TOP + 8.0                                   # carrier bottom = top of the M3 x 8 standoffs
Z_L, Z_U = P["out_seat_lo"], P["out_seat_hi"]
RD_ = P["riser_d"]; RR = P["riser_r"]
ANG = {"OUT2": -53.95, "OUT4": 53.95, "OUT1": -140.08, "OUT3": 140.08}   # direction T -> seat (deg)
SEAT = {}
for k, a in ANG.items():
    tx, ty = OUTT[k]; SEAT[k] = (round(tx + RD_ * math.cos(math.radians(a)), 3), round(ty + RD_ * math.sin(math.radians(a)), 3), Z_L if k in ("OUT2", "OUT4") else Z_U)
LUGANG = {"OUT2": 172.0, "OUT4": 188.0, "OUT1": 166.0, "OUT3": 194.0}   # e1a
LANE = {"OUT2": -43.3, "OUT1": -37.8, "OUT3": -28.7, "OUT4": -23.2}   # e1a; insulated wire may touch plastic (Dan 2026-11-13)
def obround(p, q, r, z0, z1):
    a_, b_ = Vector(p[0], p[1], 0), Vector(q[0], q[1], 0); d = b_ - a_; Lo = d.length; ang = math.degrees(math.atan2(d.Y, d.X)); m = (a_ + b_) * 0.5
    return extrude(Pos(m.X, m.Y, z0) * Rot(0, 0, ang) * SlotCenterToCenter(Lo, 2 * r), amount=z1 - z0).solid()
def slot_along(x, y, ang, wd, Ls, z0, z1):
    pl = Plane(origin=(x, y, z0), x_dir=(math.cos(math.radians(ang)), math.sin(math.radians(ang)), 0), z_dir=(0, 0, 1))
    return extrude(pl * Pos(Ls / 2, 0) * Rectangle(Ls, wd), amount=z1 - z0).solid()
def riser_local(H):
    """riser in its own frame: T centre at the origin, seat on +X at riser_d, z 0 = REDCUBE top"""
    ft_ = P["riser_foot"]
    RF = P["riser_foot_r"]
    foot = obround((0, 0), (RD_, 0), RF, 0, ft_); col = cyl(2 * RR, (RD_, 0, 0), H)
    # column-root fillet R0.5 (= cutter corner radius) where the column meets the foot-arm top: built as a concave ring
    # (revolved quarter-round profile r 4..4.5) clipped to the foot outline (OCC's fillet fails where the column and the arm end are tangent)
    rf = P["riser_root_r"]; e_ = 0.05                       # ring reaches 0.05 into the column and the arm so the fuse is volumetric
    prof = Wire([Line((RD_ + RR - e_, 0, ft_ - e_), (RD_ + RR + rf, 0, ft_ - e_)), Line((RD_ + RR + rf, 0, ft_ - e_), (RD_ + RR + rf, 0, ft_)),
                 CenterArc((RD_ + RR + rf, 0, ft_ + rf), rf, 270, -90).rotate(Axis((RD_ + RR + rf, 0, ft_ + rf), (1, 0, 0)), 90),
                 Line((RD_ + RR, 0, ft_ + rf), (RD_ + RR - e_, 0, ft_ + rf)), Line((RD_ + RR - e_, 0, ft_ + rf), (RD_ + RR - e_, 0, ft_ - e_))])
    ring = revolve(Face(prof), Axis((RD_, 0, 0), (0, 0, 1)), 360).solid()
    ring = isect(ring, obround((0, 0), (RD_, 0), RF, ft_ - e_, ft_ + rf + 0.01))
    rb = foot.fuse(col, ring)                                # one 3-way fuse, no .clean(): fusing in two steps or cleaning leaves an invalid solid
    if not rb.is_valid: rb = rb.fix()
    print("riser H", round(H, 2), "valid", rb.is_valid, "solids", len(rb.solids()), flush=True)
    rb = rb.cut(cyl(4.5, (0, 0, -0.1), ft_ + 0.2))                                                     # M4 clearance at the foot
    z_td = H - 10.0 if H - 10.0 >= 1.5 else -0.1          # v2c: the low riser (10.27) left a 0.27 floor under a 10-deep drill: drill it through
    rb = rb.cut(cyl(3.3, (RD_, 0, z_td), H - z_td + 0.1))                                              # M4 tap drill 3.3 (lug screw, tap 8 deep)
    assert rb.is_valid, f"riser H {H} invalid"
    return one(rb)
part("CPDM-ENC-107", riser_local(Z_L - TTOP), "Copper offset riser, low (OUT2 / OUT4)", f"foot arm R3.75 x 4 + seat column dia 8 at {RD_:g} from the foot hole, height {Z_L - TTOP:.2f}, M4 tap 8 (drill 3.3 through), R0.5 root", "C110 copper", "made")
part("CPDM-ENC-108", riser_local(Z_U - TTOP), "Copper offset riser, high (OUT1 / OUT3)", f"foot arm R3.75 x 4 + seat column dia 8 at {RD_:g} from the foot hole, height {Z_U - TTOP:.2f}, M4 tap 8 (drill 3.3 x 10), R0.5 root", "C110 copper", "made")
item("copper-risers-OUT1-4-low", "CPDM-ENC-107", [L(OUTT[k][0], OUTT[k][1], TTOP, rz=ANG[k]) for k in ("OUT2", "OUT4")], (0.85, 0.5, 0.25))
item("copper-risers-OUT1-4-high", "CPDM-ENC-108", [L(OUTT[k][0], OUTT[k][1], TTOP, rz=ANG[k]) for k in ("OUT1", "OUT3")], (0.85, 0.5, 0.25))
for k, (sx, sy, sz) in SEAT.items():
    tx, ty = OUTT[k]
    screw("M4", 6.0, L(tx, ty, TTOP + P["riser_foot"]))                    # foot screw: 2.0 into the 2.5 REDCUBE thread, max 1.2 N*m
    screw("M4", 8.0, L(sx, sy, sz + P["out_lug_t"]))                        # lug screw into the copper seat (7 mm engagement)
CX0, CXM, CX1, CY0, CY1 = 20.0, 36.5, 58.0, -53.4, -13.14   # e1a carrier outline
ZCL, ZCU = Z_L + P["pocket_d"], Z_U + P["pocket_d"]
car = dblock(CX0, CXM + 1.0, CY0, CY1, Z_CB, ZCL, r=3)
car = car.fuse(dblock(CXM, CX1, CY0 + 1.5, CY1 - 1.5, Z_CB, ZCU, r=3))
for (X, Y) in ANCH:
    yA, yB = (CY1 - 8, Y + 6) if Y > CY1 - 3 else (Y - 6, CY0 + 8)
    car = car.fuse(dblock(X - 14, X + 6, min(yA, yB), max(yA, yB), Z_CB, Z_CB + P["ear_t"], r=3))
for k, (sx, sy, sz) in SEAT.items():
    tx, ty = OUTT[k]
    car = car.cut(obround((tx, ty), (sx, sy), P["riser_foot_r"] + 0.1, Z_CB - 1, 80)).cut(cyl(2 * (RR + 0.1), (sx, sy, Z_CB - 1), 81))   # key slot = riser outline + 0.1
    car = car.cut(cyl(11.0, (sx, sy, sz), 40)).cut(slot_along(sx, sy, LUGANG[k], P["out_lug_w"] + 1.0, 40.0, sz, 80))   # lug ring pocket + tongue slot
for (X, Y) in ANCH:
    car = car.cut(cyl(3.4, (X, Y, Z_CB - 1), 20)).cut(cyl(6.5, (X, Y, Z_CB + P["ear_t"] - 3.2), 10))
    screw("M3", 8.0, L(X, Y, Z_CB + P["ear_t"] - 3.2))
made("carrier-G10-OUT1-4", "CPDM-ENC-109", car, (0.75, 0.78, 0.55), "OUT1-4 riser carrier",
     "3-axis machined: keys the 4 risers, solid walls between the lugs, takes lug torque; bolted to M3 x 8 standoffs on board B H2/H4", "G10 / FR4 glass-epoxy")
part("CPDM-BUY-302", standoff_mf(5.5, 8.0, 3.0, 6.0, 6.0, (0, 0, 0)), "M3 x 8 hex standoff male-female AF5.5", "M3 M-F hex standoff 8 mm (e.g. Wurth WA-SSTIE series), maker PN TBD (buy to spec)", "brass Ni", "bought", maker="(TBD)")
item("standoffs-M3x8-MF-carrier", "CPDM-BUY-302", [L(X, Y, Z_TOP) for (X, Y) in ANCH], (0.8, 0.7, 0.3))
M6_EXT_TOP = P["collar_top"] + 1.0; M4_EXT_TOP = Z_U
# OUT1-4 ring lugs (Phoenix Contact 3240083 = C-RC 6/M4 DIN, M4, 6 mm2 / 10 AWG) from the maker STEP (phoenixcontact.com product
# page, Downloads > CAD data, pxc_3240083_00_00_C-RC-6-M4-DIN_3D.stp "simplified 3D model", 2023-11-23, sha256 7a7b9f8f...).
# Maker frame: tongue z 0..1, ring (hole dia 4.3, OD 8) centre at (4, 14), barrel (OD 5.6, bottom flush with the tongue
# underside) toward -y, overall 18. Part frame (unchanged): ring centre at the origin, barrel along +x, tongue z 0..1.
def ring_lug_local():
    s = vstep("Phoenix_3240083/pxc_3240083_00_00_C-RC-6-M4-DIN_3D.stp")
    hole = [f.center() for f in s.faces() if f.geom_type.name == "CYLINDER" and abs(f.radius - 2.15) < 0.01]
    cx, cy = sum(c.X for c in hole) / len(hole), sum(c.Y for c in hole) / len(hole)
    b = bbx(s); bar = max(f.radius for f in s.faces() if f.geom_type.name == "CYLINDER" and f.radius < 3.5)
    t = min(f.center().Z for f in s.faces() if f.geom_type.name == "PLANE" and abs(f.normal_at().Z) > 0.99 and f.center().Z > 0.5)
    P.update(out_lug_L=round(cy - b.ymin, 3), out_barrel_d=round(2 * bar, 3), out_lug_t=round(t, 3), out_lug_w=round(b.xlen, 3))
    assert abs(P["out_lug_L"] - 14.0) < 0.1 and abs(P["out_barrel_d"] - 5.6) < 0.1 and abs(P["out_lug_t"] - 1.0) < 0.05 and abs(P["out_lug_w"] - 8.0) < 0.05, P
    return s.moved(Plane(origin=(cy, -cx, 0), x_dir=(0, 1, 0), z_dir=(0, 0, 1)).location)
part("3240083", ring_lug_local(), "Phoenix Contact ring cable lug C-RC 6/M4 DIN", "M4 ring lug, 6 mm2 (10 AWG), non-insulated; Phoenix Contact maker STEP (simplified)",
     "copper, tin plated", "bought", maker="Phoenix Contact", source="phoenixcontact.com 3240083 Downloads > CAD data (pxc_3240083_00_00_C-RC-6-M4-DIN_3D.stp)")
item("ring-lugs-OUT1-4", "3240083", [L(sx, sy, sz, rz=LUGANG[k]) for k, (sx, sy, sz) in SEAT.items()], (0.85, 0.6, 0.3))
XE = LX0 - 15.0
owires = []
for k, (sx, sy, sz) in SEAT.items():
    d = Vector(math.cos(math.radians(LUGANG[k])), math.sin(math.radians(LUGANG[k])), 0)
    e = Vector(sx, sy, sz + P["out_barrel_d"] / 2) + d * P["out_lug_L"]; wz = sz + P["out_barrel_d"] / 2
    owires.append(tube([(e.X, e.Y, wz), (min(e.X - 6.0, 20.0), LANE[k], wz), (XE, LANE[k], wz)], P["out_wire_d"]))
made("wires-OUT1-4-10AWG", "CPDM-HAR-201", Compound(owires), (0.75, 0.1, 0.1), "OUT1-4 wires (4 x 10 AWG GXL)",
     "31 A each, two tiers out through the lid wire-way to the west edge; routing ASSUMED, OD 4.2 ASSUMED", "10 AWG GXL copper / XLPE", kind="harness")
for k, (X, Y) in T58.items(): screw("M4", 8.0, L(X, Y, TTOP + P["lug_t"]))   # T5-T8 ring lugs + M4 screws, wires to X1

# ---------------- input deck + standoffs (Grok b, unchanged) ----------------
deck = dblock(DX0, DX1, DY0, DY1, z_deck_bot, z_deck_top, r=6)
for n, x in IN_X.items(): deck = deck.cut(dblock(x + 9, x + 55, IN_Y_N - 58, IN_Y_N - 10, z_deck_bot - 1, z_deck_top + 1, r=5))
in_pts = []
for n in IN_X:
    for (hx, hy) in [(4, 60), (62, 4)]:
        X, Y = in_hole(n, hx, hy); in_pts.append((X, Y)); deck = deck.fuse(cyl(7.0, (X, Y, z_deck_top), P["in_boss"]))
for (X, Y) in in_pts: deck = deck.cut(cyl(4.0, (X, Y, z_deck_top - 2.99), P["in_boss"] + 3.0))
for n, h, (X, Y) in SO: deck = deck.cut(cyl(3.4, (X, Y, z_deck_bot - 1), P["deck_t"] + 2))
made("input-deck", "CPDM-ENC-103", deck, (0.3, 0.3, 0.33), "Input deck", "frame for the 3 input boards on M3 x 25 standoffs, M3 heat-set inserts", "MJF PA12")
part("CPDM-BUY-301", standoff_mf(5.5, P["so_m3_len"], 3.0, 6.0, 6.0, (0, 0, 0)), "M3 x 25 hex standoff male-female AF5.5", "M3 M-F hex standoff 25 mm (e.g. Wurth WA-SSTIE series), maker PN TBD (buy to spec)", "brass Ni", "bought", maker="(TBD)")
item("standoffs-M3x25-MF", "CPDM-BUY-301", [L(X, Y, Z_TOP) for (n, h, (X, Y)) in SO], (0.8, 0.7, 0.3))
for n, h, (X, Y) in SO: screw("M3", 8.0, L(X, Y, z_deck_top))
so_set = {(n, h) for (n, h, _) in SO} | {("B", "H2"), ("B", "H4")}   # carrier standoffs replace these board screws
for n, h, (X, Y) in BOSS:
    if (n, h) not in so_set: screw("M3", 8.0, L(X, Y, Z_TOP))
for (X, Y) in in_pts: screw("M3", 8.0, L(X, Y, Z_IN + 1.51))

# ---------------- wiring (flat taped ribbons, ASSUMED harness form) ----------------
REAR = {k: (X, WALL_IN + 2.54 + 19.6 + 4.0) for k, X in CONN.items()}
YR = REAR["X1"][1]
zr = Z_TOP + 7.0
wires = []
for n, xc_, xe in (("A1", None, CONN["X1"] - 6.0), ("A2", 223.0, CONN["X1"] + 6.0)):
    cx, cy = W(n, 0, 0); xc_ = xc_ or cx
    via = [(165.0, -99.5, zr + 6.0)] if n == "A2" else []
    wires.append(ribbon([(cx, cy, Z_TOP + 2.5), (xc_, cy - 8, zr), (xc_, -97.0, zr)] + via + [(xe, YR, TZ - 8)], 14.0, P["ribbon_t"]))
bx_, by_ = W("B", -1.5, -1.5)
jx = (SEAT["OUT2"][0] + RR + SEAT["OUT1"][0] - RR) / 2   # lane between the low and high copper risers (d1a)
wires.append(ribbon([(bx_, by_, Z_TOP + 2.0), (jx, by_, Z_TOP + 5.0), (jx, -60.0, Z_TOP + 5.0), (jx, -103.0, Z_TOP + 6.0), (jx, -106.0, 4.4), (CONN["X2"] - 6, -105.0, 4.4), (CONN["X2"] - 6, -103.5, TZ + 4)], 3.5, 3.5))
tx = 96.5
wires.append(ribbon([(tx, T58["T5"][1], 16.0), (tx, -97.0, 16.0), (CONN["X1"] + 14, YR, 19.0)], 12.0, 2.5))
for n, x in IN_X.items():
    wires.append(ribbon([(x + 33, DY0 + 2, z_deck_top + 8), (x + 33, DY0 - 8, TZ + 14), (CONN["X2"] + 8, YR, TZ + 14)], 10.0, 3.0))
usbc = []
UR = WALL_IN + U_TAIL                                               # cable starts at the bulkhead FPC's Y-beam end (an adapter PCB there is TBD: the maker part ends in Y-beam contacts, not a USB-C socket)
UX = USB_X - 12.0                                                    # cable runs back south 12 mm west of the FPC (FPC + Y-beam sit x +1.3..+7.4 east of the axis)
usbc.append(tube([(USB_X, UR, P["usb_z"]), (USB_X, UR + 5.0, P["usb_z"]), (UX, UR + 5.0, P["usb_z"]), (UX, -95.0, P["usb_z"]), (80.0, -95.0, P["usb_z"]), (68.0, -95.0, 22.0), (27.0, -95.0, 22.0), (27.0, -100.5, 22.0), (27.0, -100.5, 14.0), (27.0, -106.0, 9.0), (28.0, (hb.ymin + hb.ymax) / 2, HUB_Z + 3)], 4.0))
for n in ("B", "A1", "A2"):
    X, Y = W(n, -17.0974, 55.7412)
    usbc.append(tube([(hb.xmax - 4, hb.ymax + 1, HUB_Z + 3), (hb.xmax + 2, -99.0, 7.8), (X, -99.0, 7.8), (X, -97.5, Z_TOP + 1.6)], 4.0))
made("wire-ribbons", "CPDM-HAR-202", Compound(wires), (0.85, 0.75, 0.1), "Internal harness ribbons to X1 / X2",
     "A1/A2 J3 pads, B J6 pads, B T5-T8 lugs, input boards J2 -> X1 / X2, flat taped ribbons; routing ASSUMED", "TXL / GXL wire, tape", kind="harness")
made("usb-cables", "CPDM-HAR-203", Compound(usbc), (0.2, 0.2, 0.6), "USB-C cables (bulkhead -> hub -> 3 boards)", "4 mm cables, plugs not modelled; routing ASSUMED", "USB cable", kind="harness")
part("CPDM-BUY-304", box(-4, 4, -4, 4, 0.0, 2.5), "Cable tie anchor pad 8 x 8", "adhesive / screw cable-tie anchor on the sink field (k1a), maker PN TBD", "PA66", "bought", maker="(TBD)")
item("tie-points", "CPDM-BUY-304", [L(x, -107.0, 0.0) for x in (60.0, 140.0)], (0.3, 0.3, 0.33))

# ---------------- lid (MJF PA12): Grok b form, front turrets for X1/X2/USB ----------------
w = P["wall"]; dr = P["draft_deg"]; R = P["corner_r"]; TX1 = 62.0
zs, si = P["shoulder_z"], P["shoulder_in"]
outer = dblock(LX0, LX1, LY0, LY1, 0.0, zs + 0.01, r=R)
outer = outer.fuse(dblock(LX0 + si, TX1 + 10, LY0 + si, LY1 - si, zs, P["terrace_top"], r=R - si, draft=dr, tf=4))
outer = outer.fuse(dblock(TX1 - 8, LX1 - si, LY0 + si, LY1 - si, zs, P["main_top"], r=R - si, draft=dr, tf=12))
inner = dblock(LX0 + w, LX1 - w, LY0 + w, LY1 - w, -1.0, zs + 0.02, r=R - w)
inner = inner.fuse(dblock(LX0 + si + w, TX1 + 10 - w, LY0 + si + w, LY1 - si - w, zs, P["terrace_top"] - w, r=R - si - w, draft=dr, tf=1))
inner = inner.fuse(dblock(TX1 - 8 + w, LX1 - si - w, LY0 + si + w, LY1 - si - w, zs, P["main_top"] - w, r=R - si - w, draft=dr, tf=9))
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
for k, (X, Y) in FEED.items(): lid = lid.cut(cyl(16.0, (X, Y, 10), 40))
wl = dblock(CX0 - 0.6, CX1 + 0.6, CY0 - 0.6, CY1 + 0.6, ZCL - 2.0, P["terrace_top"] + 5, r=3.5)
liner = dblock(CX0 - 0.6 - w, CX1 + 0.6 + w, CY0 - 0.6 - w, CY1 + 0.6 + w, max(ZCL - 2.0, ZB1 + 0.3), P["terrace_top"] - 0.5, r=3.5 + w)
lid = lid.fuse(liner).cut(wl)
wy0, wy1 = P["wireway_y0"], P["wireway_y1"]; wff = Z_L - 0.5
ww_liner = box(LX0 + 0.5, CX0 - 0.6, wy0 - w, wy1 + w, wff - w, P["terrace_top"] - 0.5)
lid = lid.fuse(ww_liner.cut(box(LX0 - 5, CX0 + 2, wy0, wy1, wff, 200)))
lid = lid.cut(box(LX0 - 5, CX0 + 2.0, wy0, wy1, wff, P["terrace_top"] + 20))
for k, (X, Y) in FEED.items(): lid = lid.cut(cyl(16.0, (X, Y, 10), 40))
DFLAT = {}
for k, X in CONN.items():
    zlow = bbx(isect(xc[k], box(X - 30, X + 30, LY0, WALL_IN, TZ - 30, TZ))).zmin
    fl = min(43.08 / 2, max(41.45 - 43.08 / 2, TZ - zlow + 0.2)); DFLAT[k] = round(fl, 2)
    dh = cyl(43.08, (X, LY0 - 1, TZ), w + 2, (0, 1, 0)).cut(box(X - 30, X + 30, LY0 - 2, LY0 + w + 2, TZ - 40, TZ - fl))
    lid = lid.cut(dh)
uh = cyl(20.8, (USB_X, LY0 - 1, P["usb_z"]), w + 2, (0, 1, 0)).cut(box(USB_X - 15, USB_X + 15, LY0 - 2, LY0 + w + 2, P["usb_z"] + 19.4 - 10.4, P["usb_z"] + 15))
lid = lid.cut(uh)
for i in range(6):
    X = LX0 + 40 + i * (LX1 - LX0 - 80) / 5
    for side, (Y0_, Y1_) in (("S", (LY0 - 2.0, LY0 + 2.0)), ("N", (LY1 - 2.0, LY1 + 2.0))):
        if side == "S" and any(abs(X - tx_) < d / 2 + 6 for (tx_, _, d) in TURRETS): continue
        lid = lid.fuse(dblock(X - 5, X + 5, Y0_, Y1_, 0.0, 16.0, r=1.5, tf=1.5))
for i in range(7):
    X = 120 + i * 18.0
    lid = lid.cut(dblock(X - 2, X + 2, LY1 - 54, LY1 - 24, P["main_top"] - 1.2, P["main_top"] + 5, r=1.9))
for (X, Y) in LID_SCREWS:
    lid = lid.fuse(isect(cyl(9.0, (X, Y, 0), 11.0), dblock(LX0, LX1, LY0, LY1, 0, 11, r=R)))
for (X, Y) in LID_SCREWS:
    lid = lid.cut(cyl(5.6, (X, Y, -0.5), 10.5))
    screw("M4", 12.0, L(X, Y, -pt + 4.0, rx=180))
made("lid", "CPDM-ENC-102", lid, (0.18, 0.18, 0.2), "Lid", "walls 3.0, draft 6; front turrets for X1/X2/USB-C; OUT1-4 well + wire-way; M4 heat-set inserts", "MJF PA12")
part("RX-M4x8.1", cyl(5.6, (0, 0, 0), 8.1).cut(cyl(4.0, (0, 0, -0.1), 8.3)), "ruthex heat-set insert M4 x 8.1", "threaded insert OD 5.6 x 8.1 for the lid screw bosses (envelope)", "brass", "bought", maker="ruthex")
item("heat-set-inserts-M4", "RX-M4x8.1", [L(X, Y, 0.5) for (X, Y) in LID_SCREWS], (0.8, 0.65, 0.25))
for pn, locs in SCR.items():
    item("screws_" + pn, pn, locs, (0.35, 0.35, 0.38))

# ---------------- export ----------------
# 1) one STEP per part number (parts/<PN>.stp, in the part's own frame) + the assembly STEP that references them (external
#    references, one instance per placement): STEPCAFControl multi-file mode. PRODUCT name = PN, description = name | what |
#    material | maker | rev (written into the STEP PRODUCT entity after export).
import re, csv
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ColorGen
from OCP.TDataStd import TDataStd_Name
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone
from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB
ASM = f"CPDM-ENC-100-{VAR}"
def ascii_(s): return re.sub(r"[^\x20-\x7e]", "-", s).replace("'", "")
def full_desc(pn):
    c = CAT[pn]
    return ascii_(f"{c['name']} | {c['desc']} | material: {c['material'] or '-'} | maker: {c['maker']} | {c['kind']} | rev {REV}")
used = {it["pn"] for it in ITEMS.values()}
INVALID = [pn for pn, c in CAT.items() if c["kind"].startswith("made") and not all(s.is_valid for s in c["shape"].solids())]
print("invalid made parts:", INVALID or "none", flush=True)
for pn in list(CAT):
    if pn not in used: print("WARN part defined but not placed:", pn); del CAT[pn]
doc = TDocStd_Document(TCollection_ExtendedString("XmlXCAF"))
st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()); ct = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
asm = st.NewShape(); TDataStd_Name.Set_s(asm, TCollection_ExtendedString(ASM))
lab = {}
for nm, it in ITEMS.items():
    pn = it["pn"]
    if pn not in lab:
        l_ = st.AddShape(CAT[pn]["shape"].wrapped, False); TDataStd_Name.Set_s(l_, TCollection_ExtendedString(pn)); lab[pn] = l_
        ct.SetColor(l_, Quantity_Color(*it["color"], Quantity_TOC_RGB), XCAFDoc_ColorGen)
    for loc in it["locs"]: st.AddComponent(asm, lab[pn], loc.wrapped)
st.UpdateAssemblies()
XO = os.path.join(OUT, "xref"); shutil.rmtree(XO, ignore_errors=True); os.makedirs(os.path.join(XO, "parts"))
cwd = os.getcwd(); os.chdir(XO)
wr = STEPCAFControl_Writer(); wr.SetNameMode(True); wr.SetColorMode(True)
assert wr.Transfer(doc, STEPControl_AsIs, "parts/"), "STEP transfer failed"
AFILE = f"custom-pdm-enclosure-{REV}-{VAR}-assembly.step"
assert wr.Write(AFILE) == IFSelect_RetDone, "STEP write failed"
os.chdir(cwd)
# OCC's multi-file writer puts most of the session's model into EVERY external file (about 140 MB each here), so the part
# files are rewritten one by one from the part's own shape (same name, same frame); the assembly keeps its references.
for pn, c in CAT.items():
    s = c["shape"]; s.label = pn; s.color = Color(*next(it["color"] for it in ITEMS.values() if it["pn"] == pn))
    export_step(s, os.path.join(XO, "parts", pn + ".stp"))
DESC = {pn: full_desc(pn) for pn in CAT}; DESC[ASM] = ascii_(f"custom-pdm enclosure {REV} {VAR} assembly | external references to parts/*.stp | rev {REV}")
def set_desc(path):
    t = open(path, encoding="latin-1").read()
    t = re.sub(r"PRODUCT\('([^']*)','([^']*)','[^']*'", lambda m: f"PRODUCT('{m.group(1)}','{m.group(1)}','{DESC.get(m.group(1), '')}'", t)
    open(path, "w", encoding="latin-1").write(t)
for f in [os.path.join(XO, AFILE)] + [os.path.join(XO, "parts", g) for g in os.listdir(os.path.join(XO, "parts"))]: set_desc(f)
# 2) world-placed BREP per item (checks, renders) + a flat single-file copy of the assembly for viewers (convenience only)
kids = []
for nm, it in ITEMS.items():
    s = world(nm); s.label = nm.replace(" ", "_"); s.color = Color(*it["color"]); kids.append(s)
    export_brep(s, os.path.join(OUT, "brep", nm.replace(" ", "_") + ".brep"))
export_step(Compound(children=kids, label=f"custom-pdm-enclosure-{REV}-{VAR}-flat"), os.path.join(OUT, f"custom-pdm-enclosure-{REV}-{VAR}-assembly-flat.step"))
# 3) BOM from the placements
qty = {}
for it in ITEMS.values(): qty[it["pn"]] = qty.get(it["pn"], 0) + len(it["locs"])
order = {"made": 0, "made-set": 1, "harness": 2, "board": 3, "bought": 4, "bought-drawn": 5}
bom = sorted(CAT, key=lambda pn: (order.get(CAT[pn]["kind"], 9), pn))
with open(os.path.join(OUT, f"BOM-{REV}-{VAR}.csv"), "w", newline="") as fh:
    cw = csv.writer(fh); cw.writerow(["part_number", "qty", "name", "maker", "kind", "material", "description", "file", "model_source"])
    for pn in bom:
        c = CAT[pn]; cw.writerow([pn, qty[pn], c["name"], c["maker"], c["kind"], c["material"], c["desc"], f"parts/{pn}.stp", c["source"]])
def mat4(loc):
    t = loc.wrapped.Transformation()
    return [round(t.Value(r, c), 9) for r in (1, 2, 3) for c in (1, 2, 3, 4)] + [0, 0, 0, 1]
def loc_info(loc):
    p0 = Vertex(0, 0, 0).moved(loc).center(); p1 = Vertex(0, 0, 1).moved(loc).center(); a = p1 - p0
    return [round(p0.X, 4), round(p0.Y, 4), round(p0.Z, 4)], [round(a.X, 6), round(a.Y, 6), round(a.Z, 6)]
bb = bbx(Compound([world(nm) for nm in ITEMS if not nm.startswith("vendor-plug")]))
lb = bbx(world("lid")); sb = bbx(world("heat-sink"))
meta = dict(variant=VAR, rev=REV, P=P, Z_BOT=Z_BOT, Z_TOP=Z_TOP, X0=X0, M6TOP=M6TOP, TTOP=TTOP, M6_EXT_TOP=M6_EXT_TOP, M4_EXT_TOP=M4_EXT_TOP,
            OUT_SEAT=SEAT, OUT_LUGANG=LUGANG, OUT_RISER_ANG=ANG, CARRIER=dict(x=(CX0, CXM, CX1), y=(CY0, CY1), z=(Z_CB, ZCL, ZCU), anchors=ANCH),
            footprint=(LX0, LX1, LY0, LY1), lid_bbox=(lb.xmin, lb.xmax, lb.ymin, lb.ymax, lb.zmin, lb.zmax),
            sink_bbox=(sb.xmin, sb.xmax, sb.ymin, sb.ymax, sb.zmin, sb.zmax), overall_no_plugs=(bb.xmin, bb.xmax, bb.ymin, bb.ymax, bb.zmin, bb.zmax),
            CONN=CONN, USB_X=USB_X, FEED=FEED, OUTT=OUTT, T58=T58, fan=fan_info, feet=FEET, lid_screws=LID_SCREWS,
            would_strip=dict(A_J3=dA, B_J6=dB), d_flat_below_centre=DFLAT, hub_bbox=[hb.xmin, hb.xmax, hb.ymin, hb.ymax], standoffs=[(n, h) for n, h, _ in SO],
            colors={k: it["color"] for k, it in ITEMS.items()}, items={k: dict(pn=it["pn"], n=len(it["locs"])) for k, it in ITEMS.items()},
            parts={pn: dict(qty=qty[pn], name=c["name"], maker=c["maker"], kind=c["kind"], material=c["material"], desc=DESC[pn]) for pn, c in CAT.items()},
            assembly=dict(file=f"xref/{AFILE}", name=ASM), screws=[dict(size=s, L=Lg, at=loc_info(l)[0], axis=loc_info(l)[1]) for (s, Lg, l) in SCREWS],
            placements={nm: dict(pn=it["pn"], m=[mat4(l) for l in it["locs"]]) for nm, it in ITEMS.items()},   # 4x4 row-major, mm (Fusion insert)
            invalid_made_parts=INVALID, n_fins=len(fins), riser_d={k: round(math.dist(SEAT[k][:2], OUTT[k]), 3) for k in SEAT})
json.dump(meta, open(os.path.join(OUT, "meta.json"), "w"), indent=1, default=str)
print("done", VAR, len(ITEMS), "items", len(CAT), "part numbers", "overall(no plugs)", [round(v, 1) for v in meta["overall_no_plugs"]], "would-strip", dA, dB)
