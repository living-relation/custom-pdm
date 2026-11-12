"""custom-pdm enclosure, low-profile v1 (build123d, handbuilt-cad CAD venv, DansPC WSL).

Usage:  $CAD_PY build_lowpro.py     (env: RUN_DIR = output folder, REF_BOARDS = board STEP folder, see README)
Design rules: DECISIONS.md 2026-11-11 / 2026-11-12 (e1-e7, j1a, e4a, b1b, p2a, k1a, a1a, a2b, x1a, x2c, v2b, y1a).
Frame: X along the length (left end -> right end), Y across (front wall = -Y), Z up, mm.
Z = 0 is the heat-sink field (base plate top). Board naming (DECISIONS 2026-11-12): top / bottom = surfaces;
front edge = PCB -Y (faces the front wall), back edge = PCB +Y, left / right end = PCB -X / +X.
Boards are turned 180 deg about Z so their front edge faces -Y: world X = TX - x_kicad, world Y = y_kicad.
ASSUMED = my choice, TBD = not confirmed by a primary source (both listed in docs/enclosure-3d.md).
"""
import os, json
from build123d import *

REF = os.environ.get("REF_BOARDS", os.path.expanduser("~/scratch/encl-lowpro/work/reference/boards"))
OUT = os.environ.get("RUN_DIR", os.path.expanduser("~/scratch/encl-lowpro/runs/v1"))
for d in ("parts", "brep"):
    os.makedirs(os.path.join(OUT, d), exist_ok=True)

# ---------------- driving dimensions (ASSUMED unless noted) ----------------
P = dict(
    gap_boards=2.0,                 # board-to-board gap
    ped_h=3.0, pad_t=1.0,           # pedestal height, gap pad (product TBD)
    plate_t=8.0,                    # base plate
    fin_h=25.0, fin_t=2.0, fin_pitch=6.0,   # fins DOWN, along X, 4 mm channels
    fan_zone=75.0,                  # left-end plenum length (no fins) for the fan
    cover_t=1.5, foot_h=10.0, foot_d=16.0,  # duct cover sheet on the fin tips; feet below it (fan intake gap)
    wall=3.0, lid_top=60.0, lid_r=10.0, lid_fillet=6.0,
    clr_left=6.0, clr_right=6.0, clr_back=14.0, clr_front=35.0,  # inner clearances board -> lid inner wall (back: right-angle USB-C plugs)
    ledge=34.0,                     # stud ledge outside the lid at each end (left: BATT / GND, right: OUT1-4)
    bar_w=20.0, bar_t=3.0,          # BATT / GND bars (b1b: 150 A target)
    in_boss=4.0,                    # input-board bosses from the lid ceiling
)
Z_BOT = P["ped_h"] + P["pad_t"]                 # board bottom 4.0
T_PCB = 1.769872                                # board thickness (KiCad board setup)
Z_TOP = Z_BOT + T_PCB
M6_TOP = Z_BOT + 15.23                          # Wuerth 7461084 top above board bottom (board STEP)
T_TOP = Z_BOT + 4.73                            # REDCUBE 74650074R top above board bottom (board STEP; 3.0 above the top surface)
A_XMIN, A_XMAX, B_XMAX = -37.846, 34.544, 73.544   # KiCad board outlines (x); all boards y -33.274 .. 61.976
Y_FRONT, Y_BACK = -33.274, 61.976
TX = {"A1": A_XMAX}                             # A1 world span 0 .. 72.39
TX["A2"] = TX["A1"] - A_XMIN + P["gap_boards"] + A_XMAX
TX["B"] = TX["A2"] - A_XMIN + P["gap_boards"] + B_XMAX
def Wk(n, xk, yk): return (TX[n] - xk, yk)
def span(n): return (TX[n] - (B_XMAX if n == "B" else A_XMAX), TX[n] - A_XMIN)
XL, XR = span("A1")[0], span("B")[1]

parts = {}
def one(s):
    so = s.solids(); return so[0] if len(so) == 1 else Compound(list(so))
def addp(name, shape, color, label, step=True):
    parts[name] = dict(shape=shape if name.startswith(("board", "input-board")) else one(shape), color=color, label=label, step=step)
def box(x0, x1, y0, y1, z0, z1):
    x0, x1 = sorted((x0, x1)); y0, y1 = sorted((y0, y1)); z0, z1 = sorted((z0, z1))
    return Solid.make_box(x1 - x0, y1 - y0, z1 - z0, Plane(origin=(x0, y0, z0)))
def cyl(d, p0, L, axis=(0, 0, 1)):
    return Solid.make_cylinder(d / 2, L, Plane(origin=p0, z_dir=axis))
def rbox(x0, x1, y0, y1, z0, z1, r):
    sk = Pos((x0 + x1) / 2, (y0 + y1) / 2, z0) * RectangleRounded(x1 - x0, y1 - y0, r)
    return extrude(sk, amount=z1 - z0).solid()
def isect(a, b):
    r = a.intersect(b)
    if isinstance(r, list): r = r[0] if len(r) == 1 else Compound(list(r))
    return r
def bbx(s):
    b = s.bounding_box(); return (b.min.X, b.max.X, b.min.Y, b.max.Y, b.min.Z, b.max.Z)

# ---------------- boards (KiCad STEP exports, see README) ----------------
def filt(s, board):
    keep = []
    for so in s.solids():
        x0, x1, y0, y1, z0, z1 = bbx(so); cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if board == "A":
            if z1 > 20 and abs(cx) < 1 and abs(cy) < 1: continue                         # DT15-12PA housing (a1a)
            if abs(cx) < 13 and abs(cy) < 7 and (x1 - x0) < 2.5 and (y1 - y0) < 2.5 and z0 < -0.5: continue  # J3 pins
        if board == "B" and abs(cx) < 4 and abs(cy) < 4 and (x1 - x0) < 12 and z1 > 3: continue   # J6 Micro-Fit (a2b)
        keep.append(so)
    return Compound(keep)
stepA = filt(import_step(os.path.join(REF, "board-A.step")), "A")
stepB = filt(import_step(os.path.join(REF, "board-B.step")), "B")
stepI = import_step(os.path.join(REF, "input-board.step"))
for n in ("A1", "A2", "B"):
    s = (stepB if n == "B" else stepA).rotate(Axis.Z, 180).translate(Vector(TX[n], 0, Z_BOT))
    addp(f"board-{n}", s, (0.1, 0.45, 0.15), "KiCad STEP export (board-fix era), J3 / J6 bodies removed (a1a, a2b)", step=False)

# ---------------- footprint of lid and base ----------------
w = P["wall"]
LX0, LX1 = XL - P["clr_left"] - w, XR + P["clr_right"] + w
LY0, LY1 = Y_FRONT - P["clr_front"] - w, Y_BACK + P["clr_back"] + w
BX0, BX1 = LX0 - P["ledge"], LX1 + P["ledge"]
pt = P["plate_t"]; zf = -pt - P["fin_h"]; zc = zf - P["cover_t"]

# ---------------- base = heat sink (6061/6063 Al, one machined part) ----------------
base = rbox(BX0, BX1, LY0, LY1, -pt, 0, 6.0)
PED = {"A": [(-1.905, 13.132, 11.379, 14.021), (-1.981, 10.922, -13.970, -11.227)],
       "B": [(-12.22, 12.32, 11.15, 14.07), (-12.22, 12.32, -14.07, -11.15), (53.623, 56.265, -27.415, 46.417)]}
pads, peds = [], []
for n in ("A1", "A2", "B"):
    for (a, b, c, d) in PED["B" if n == "B" else "A"]:
        (xa, ya), (xb, yb) = Wk(n, a - 1.5, c - 1.5), Wk(n, b + 1.5, d + 1.5)
        peds.append((min(xa, xb), max(xa, xb), min(ya, yb), max(ya, yb)))
        base = base.fuse(box(xa, xb, ya, yb, 0, P["ped_h"]))
        pads.append(box(xa, xb, ya, yb, P["ped_h"], Z_BOT))
HOLES = {"H1": (-33.02, 21.59), "H2": (26.67, -21.59), "H3": (-21.082, -21.59), "H4": (26.67, 21.59)}
HOLES_B = {"H5": (69.044, -10.684), "H6": (69.044, 35.896)}
BOSS = []
for n in ("A1", "A2", "B"):
    hs = dict(HOLES); hs.update(HOLES_B if n == "B" else {})
    for h, (x, y) in hs.items(): BOSS.append(Wk(n, x, y))
for (X, Y) in BOSS:
    base = base.fuse(cyl(6.0, (X, Y, 0), Z_BOT)).cut(cyl(2.5, (X, Y, Z_BOT - 8.0), 8.01))   # M3 tapped, 8 deep
fins, y = [], LY0
while y + P["fin_t"] <= LY1 + 1e-6:
    fins.append(y); y += P["fin_pitch"]
if LY1 - (fins[-1] + P["fin_t"]) > 0.5: fins.append(LY1 - P["fin_t"])
FX0 = BX0 + P["fan_zone"]
FEET = [(BX0 + 12, LY0 + 12), (BX0 + 12, LY1 - 12), (BX1 - 12, LY0 + 12), (BX1 - 12, LY1 - 12)]
fs = []
for i, y in enumerate(fins):
    side = i == 0 or i == len(fins) - 1
    near_foot = any(y < fy + P["foot_d"] / 2 + 2 and y + P["fin_t"] > fy - P["foot_d"] / 2 - 2 for fy in (LY0 + 12, LY1 - 12))
    x1 = BX1 - 12 - P["foot_d"] / 2 - 2 if (near_foot and not side) else BX1
    fs.append(box(BX0 if side else FX0, x1, y, y + P["fin_t"], zf, -pt))
fs.append(box(BX0, BX0 + 2.0, LY0, LY1, zf, -pt))                          # plenum end wall (left end)
base = base.fuse(*fs)
for (X, Y) in FEET:
    base = base.fuse(cyl(P["foot_d"], (X, Y, zc - P["foot_h"]), P["fin_h"] + P["cover_t"] + P["foot_h"]))
    base = base.cut(cyl(6.6, (X, Y, zc - P["foot_h"] - 1), P["fin_h"] + P["foot_h"] + pt + 4))   # M6 clearance, mounting
# lid screws: X picked clear of the front-wall connectors and the boards' back-edge USB-C plugs
LID_SCREWS = [(X, LY0 + 5.5) for X in (14.0, 60.0, 140.0, 255.0)] + [(X, LY1 - 5.5) for X in (14.0, 85.0, 160.0, 200.0, 255.0)]
LID_SCREWS += [(LX0 + 5.5, -55.0), (LX1 - 5.5, -55.0)]   # end walls: in the front zone, clear of the board ends
for (X, Y) in LID_SCREWS:
    base = base.cut(cyl(3.3, (X, Y, -6.0), 6.01))                          # M4 tapped blind, 6 deep
TIES = [(TX[n], Y_FRONT - 12.0) for n in ("A1", "A2")]                     # k1a cable-tie posts
for (X, Y) in TIES:
    base = base.fuse(box(X - 5, X + 5, Y - 3, Y + 3, 0, 8)).cut(box(X - 2, X + 2, Y - 4, Y + 4, 2.5, 5.0))
addp("heat-sink-base", base, (0.72, 0.72, 0.76), "6061-T6 (or 6063) aluminium, one machined part: plate 8, fins down 25 x 2 @ 6, stud ledges, feet; ASSUMED sizes")
addp("gap-pads", Compound(pads), (0.95, 0.5, 0.6), "insulating gap pad 1.0, product TBD (heat model k 1-6)")
cover = box(BX0, BX1, LY0, LY1, zc, zf)
FAN_C = (BX0 + 2 + (P["fan_zone"] - 2) / 2, (LY0 + LY1) / 2)
cover = cover.cut(cyl(57.0, (FAN_C[0], FAN_C[1], zc - 1), 3))
for (X, Y) in FEET: cover = cover.cut(cyl(P["foot_d"] + 1, (X, Y, zc - 1), 3))
addp("duct-cover", cover, (0.6, 0.6, 0.62), "1.5 aluminium sheet on the fin tips: closes the channels into ducts; fan hole 57; ASSUMED")
fan = box(FAN_C[0] - 30, FAN_C[0] + 30, FAN_C[1] - 30, FAN_C[1] + 30, zf, zf + 15).cut(cyl(57.0, (FAN_C[0], FAN_C[1], zf - 1), 17))
fan = fan.fuse(cyl(28.0, (FAN_C[0], FAN_C[1], zf), 15))   # sits on the cover inside the plenum, 10 mm under the plate
addp("fan-Noctua-NF-A6x15-FLX", fan, (0.55, 0.35, 0.25), "Noctua NF-A6x15 FLX 60x60x15 12 V (19.8 dB(A), 13.77 CFM, 2.43 mmH2O, -10..+70 C); envelope; blows up into the plenum")

# ---------------- feed bars (left ledge), OUT straps (right ledge), studs (e4a, b1b, p2a) ----------------
FEED = {"BATT": (24.638, 27.178), "GND": (30.48, -27.178)}     # board M6 terminals, KiCad (A and B same)
bw, bt = P["bar_w"], P["bar_t"]
STUD = {"BATT": (BX0 + 17.0, 27.178), "GND": (BX0 + 17.0, -27.178)}
bars = {}
for k, (xk, yk) in FEED.items():
    xe = Wk("B", xk, yk)[0] + 11.0
    bars[k] = box(STUD[k][0] - 11.0, xe, yk - bw / 2, yk + bw / 2, M6_TOP, M6_TOP + bt)
    for n in ("A1", "A2", "B"):
        X, Y = Wk(n, xk, yk); bars[k] = bars[k].cut(cyl(6.6, (X, Y, M6_TOP - 1), bt + 2))
    bars[k] = bars[k].cut(cyl(8.5, (STUD[k][0], STUD[k][1], M6_TOP - 1), bt + 2))
addp("bar-BATT", bars["BATT"], (0.85, 0.5, 0.25), "Cu-ETP bar 20 x 3 (60 mm2), left-ledge stud to the three boards' +12 V M6 terminals; ASSUMED")
addp("bar-GND", bars["GND"], (0.55, 0.4, 0.3), "Cu-ETP bar 20 x 3 (60 mm2), left-ledge stud to the three boards' GND M6 terminals; ASSUMED")
T = {"Tm-": (-12.0, -4.75), "Tm+": (-12.0, 4.75), "To-": (12.0, -4.75), "To+": (12.0, 4.75)}   # board B REDCUBE T1-T4; m = nearer the power end
XO = LX1 + 17.0
OUTS = {"Tm-": (XO, -12.0), "Tm+": (XO, 12.0), "To-": (XO, -40.0), "To+": (XO, 40.0)}
SW = {"m": (8.0, 2.0), "o": (5.0, 3.0)}          # strap width x thickness: 16 / 15 mm2 for 31 A (ASSUMED)
def strap(pts, sw, st):
    s = None
    for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
        seg = box(min(xa, xb) - sw / 2, max(xa, xb) + sw / 2, min(ya, yb) - sw / 2, max(ya, yb) + sw / 2, T_TOP, T_TOP + st)
        s = seg if s is None else s.fuse(seg)
    return s
straps, SLOTS = [], []
for t, (xk, yk) in T.items():
    X, Y = Wk("B", xk, yk); sx, sy = OUTS[t]; sg = 1 if sy > 0 else -1; sw, st = SW[t[1]]
    if t[1] == "m":
        pts = [(X, Y), (258.0, Y), (258.0, sy), (sx, sy)]; SLOTS.append((sy, sw, st))
    else:
        yo = sg * 19.5
        pts = [(X, Y), (X, yo), (LX1 + 6.0, yo), (LX1 + 6.0, sy), (sx, sy)]; SLOTS.append((yo, sw, st))
    straps.append(strap(pts, sw, st).cut(cyl(4.4, (X, Y, T_TOP - 1), st + 2)).cut(cyl(6.6, (sx, sy, T_TOP - 1), st + 2)))
addp("straps-OUT1-4", Compound(straps), (0.85, 0.55, 0.3), "Cu-ETP straps, middle 8 x 2, outer 5 x 3 (16 / 15 mm2 for 31 A), M4 hole on the REDCUBE terminal, M6 at the stud; ASSUMED")
studs, blocks = [], []
for k, (X, Y) in STUD.items():
    blocks.append(rbox(X - 11, X + 11, Y - 11, Y + 11, 0, M6_TOP, 3))
    studs.append(cyl(8.0, (X, Y, M6_TOP - 12), 12 + bt + 22))
for t, (X, Y) in OUTS.items():
    blocks.append(rbox(X - 8, X + 8, Y - 8, Y + 8, 0, T_TOP, 2.5))
    studs.append(cyl(6.0, (X, Y, 0.0), T_TOP + 3.0 + 18))
addp("stud-blocks", Compound(blocks), (0.25, 0.3, 0.25), "G10 insulating blocks on the Al ledges (studs insulated from the base); ASSUMED")
addp("studs", Compound(studs), (0.8, 0.75, 0.45), "BATT / GND M8 studs (Blue Sea 2202 / 2201 per C5, real geometry TBD), OUT1-4 M6 studs; stud up, lug flat (t1a)")

# ---------------- lid (MJF PA12, e2a) ----------------
lid_o = rbox(LX0, LX1, LY0, LY1, 0, P["lid_top"], P["lid_r"])
lid_o = lid_o.fillet(P["lid_fillet"], lid_o.faces().sort_by(Axis.Z)[-1].edges())
lid = lid_o.cut(rbox(LX0 + w, LX1 - w, LY0 + w, LY1 - w, -1, P["lid_top"] - w, P["lid_r"] - w))
for (X, Y) in LID_SCREWS:      # bosses, counterbored from the top for SHCS M4 into the base plate
    lid = lid.fuse(isect(cyl(10.0, (X, Y, 0), P["lid_top"] - w), lid_o))
    lid = lid.cut(cyl(4.5, (X, Y, -1), P["lid_top"] + 2)).cut(cyl(8.0, (X, Y, 6.0), P["lid_top"]))
XC = {"X1": ((span("A1")[1] + span("A2")[0]) / 2 + 30.0, 31.0), "X2": (span("B")[0] + 28.0, 31.0), "USB": (span("B")[0] + 78.0, 31.0)}
CUT = {"X1": 36.0, "X2": 36.0, "USB": 17.0}                     # panel cut-outs TBD (TE / Amphenol drawings not read)
for k, (X, Z) in XC.items():
    lid = lid.cut(cyl(CUT[k], (X, LY0 - 1, Z), w + 2, axis=(0, 1, 0)))
for k, (xk, yk) in FEED.items():       # bar pass-throughs, left wall (gasket / potting TBD)
    lid = lid.cut(box(LX0 - 1, LX0 + w + 1, yk - bw / 2 - 1, yk + bw / 2 + 1, M6_TOP - 1, M6_TOP + bt + 1))
for (yy, sw, st) in SLOTS:            # strap pass-throughs, right wall
    lid = lid.cut(box(LX1 - w - 1, LX1 + 1, yy - sw / 2 - 1, yy + sw / 2 + 1, T_TOP - 1, T_TOP + st + 1))
IB = {}
for n in ("A1", "A2", "B"):            # one input board under the ceiling over each main board, parts down (x2c / x2a)
    x0, x1 = span(n); IB[n] = ((x0 + x1) / 2 - 33.0, (Y_FRONT + Y_BACK) / 2 - 32.0)
z_ceil = P["lid_top"] - w; z_ib_back = z_ceil - P["in_boss"]
for n, (x0, y0) in IB.items():
    for (hx, hy) in ((4.0, 60.0), (62.0, 4.0)):        # input board M3 holes, KiCad coords (board 66 x 64)
        X, Y = x0 + hx, y0 + (64.0 - hy)
        lid = lid.fuse(cyl(7.0, (X, Y, z_ib_back), P["in_boss"] + 0.5)).cut(cyl(4.0, (X, Y, z_ib_back - 0.1), 4.0))
    s = stepI.rotate(Axis.X, 180).translate(Vector(x0, y0, z_ib_back))
    addp(f"input-board-{n}", s, (0.1, 0.35, 0.55), "KiCad STEP of the input board, upside down (parts toward the main board)", step=False)
addp("lid", lid, (0.18, 0.18, 0.2), "MJF PA12 lid, wall / top 3, M4 screws from the top into the base; sizes ASSUMED")

def panel_conn(X, Z, fl_d, fl_t, front, back, body_d):
    s = cyl(fl_d, (X, LY0 - fl_t, Z), fl_t, axis=(0, 1, 0))
    s = s.fuse(cyl(body_d, (X, LY0 - front, Z), front - fl_t, axis=(0, 1, 0)))
    return s.fuse(cyl(body_d, (X, LY0, Z), back + w, axis=(0, 1, 0)))
addp("X1-HD34-24-21SN-envelope", panel_conn(*XC["X1"], 50.8, 2.5, 14.0, 28.0, 34.0), (0.55, 0.55, 0.6),
     "SIMPLIFIED envelope: flange 50.8 (TE catalog), 28 behind the wall ASSUMED, cut-out TBD")
addp("X2-HDP24-24-47SE-envelope", panel_conn(*XC["X2"], 50.8, 2.5, 26.0, 30.0, 34.0), (0.55, 0.55, 0.6),
     "SIMPLIFIED envelope: 26.2 in front, about 30 behind (TE drawing -L015), cut-out TBD")
addp("USB-C-bulkhead-envelope", panel_conn(*XC["USB"], 24.0, 3.0, 10.0, 20.0, 15.0), (0.3, 0.3, 0.32),
     "SIMPLIFIED IP67 jam-nut USB-C panel receptacle envelope (Amphenol LTW UC / USC family, PN and cut-out TBD)")
HUB = (XC["USB"][0] - 16.0, LY0 + w + 12.0)
hub = box(HUB[0], HUB[0] + 31.6, HUB[1], HUB[1] + 20.4, 4.0, 8.8)
for (dx, dy) in ((3, 3), (28.6, 3), (3, 17.4), (28.6, 17.4)): hub = hub.fuse(cyl(4.5, (HUB[0] + dx, HUB[1] + dy, 0), 4.0))
addp("USB-hub-Adafruit-5997-envelope", hub, (0.15, 0.15, 0.5), "Adafruit 5997 CH334F mini 4-port hub 31.6 x 20.4 x 4.8 on 4 mm standoffs; bus powered (y1a)")

# ---------------- export ----------------
kids = []
for nm, d in parts.items():
    s = d["shape"]; s.label = nm; s.color = Color(*d["color"]); kids.append(s)
    export_brep(s, os.path.join(OUT, "brep", nm + ".brep"))
    if d["step"]: export_step(s, os.path.join(OUT, "parts", nm + ".step"))
export_step(Compound(children=kids, label="custom-pdm-enclosure-lowpro-v1"), os.path.join(OUT, "custom-pdm-enclosure-lowpro-v1-assembly.step"))
export_step(Compound(children=[k for k in kids if not k.label.startswith(("board", "input-board"))], label="noboards"),
            os.path.join(OUT, "custom-pdm-enclosure-lowpro-v1-noboards.step"))
DENS = {"heat-sink-base": 2.70, "duct-cover": 2.70, "lid": 1.01, "bar-BATT": 8.93, "bar-GND": 8.93, "straps-OUT1-4": 8.93, "stud-blocks": 1.85}
mass = {k: round(parts[k]["shape"].volume * DENS[k] / 1000.0, 1) for k in DENS}
ov = bbx(Compound([d["shape"] for d in parts.values() if d["step"]]))
meta = dict(P=P, Z_BOT=Z_BOT, Z_TOP=Z_TOP, M6_TOP=M6_TOP, T_TOP=T_TOP, TX=TX, lid=(LX0, LX1, LY0, LY1, 0, P["lid_top"]),
            base=(BX0, BX1, LY0, LY1, zc - P["foot_h"], 0), fin_x=(FX0, BX1), fins_y=fins, fan_c=FAN_C, peds=peds,
            overall=ov, XC=XC, STUD=STUD, OUTS=OUTS, TIES=TIES, IB=IB, HUB=HUB, mass_g=mass, n_fins=len(fins),
            colors={k: d["color"] for k, d in parts.items()}, labels={k: d["label"] for k, d in parts.items()})
json.dump(meta, open(os.path.join(OUT, "meta.json"), "w"), indent=1, default=str)
print("overall", [round(v, 1) for v in ov], "size", round(ov[1] - ov[0], 1), round(ov[3] - ov[2], 1), round(ov[5] - ov[4], 1))
print("mass g", mass, "total", round(sum(mass.values()), 0))
