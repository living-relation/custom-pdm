"""Draw the first enclosure layout PROPOSAL (2D plan) as an SVG illustration.

Run with the KiCad python (read-only on the boards):
  python.exe tools/gen_enclosure_layout.py [out.svg]
Default output: docs/diagrams/enclosure-layout.svg

Board geometry (outlines, holes, chips, terminals, bottom-mask windows) is read from the board files.
Vendor geometry that is not in the boards (DT15-12PA housing, connector flanges) is typed in below with its source.
The PLACEMENT numbers (margins, gaps, board order) are assumptions = open questions for Dan, see docs/enclosure-layout.md.
Everything is an illustration of a proposal, NOT a source of truth.
"""
import os
import sys

import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HW = os.path.join(ROOT, "hardware")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs", "diagrams", "enclosure-layout.svg")
mm = lambda v: v / 1e6

# ---- placement assumptions (open questions, see docs/enclosure-layout.md) --------------------------------
WEST = 28.0     # west wall -> board B west edge: room for the BATT / GND stud nuts and bar ends
GAP = 10.0      # between boards (bars, screwdriver access)
EAST = 10.0     # east edge margin
NORTH = 45.0    # north wall -> main-row boards: X1 body inside the wall + wire bend (TE catalog: HD34 24 receptacle length 41.86 mm)
ROWGAP = 12.0   # main row -> input-board row
SOUTH = 45.0    # input-board row -> south wall (X2 body + wire bend)
STUD_D = 20.0   # drawn stud + rubber boot diameter: TBD (stud size and boot not chosen)
# ---- vendor geometry not in the boards ------------------------------------------------------------------
DT15_HALF = (29.6, 17.63)     # DT15-12PA housing envelope about J3's origin (TE STEP c-dt15-12pa-e-3d, measured in Fusion)
DT15_FEET = [(-20.3, -14.7), (14.7, 20.3)]   # x ranges of the four 5.6 x 5.6 feet (y 7.9..13.5, both signs)
DT15_FOOT_Y = (7.9, 13.5)
FLANGE_D = 50.8               # HD34 / HDP24 size-24 receptacle: TE catalog p.147, drawing HDP24-24-XXP/SX-L015


def load(path):
    b = pcbnew.LoadBoard(path)
    edge = [d for d in b.GetDrawings() if d.GetLayerName() == "Edge.Cuts"]
    if len(edge) == 1:
        bb = edge[0].GetBoundingBox()
        outline = (mm(bb.GetX()) + 0.025, mm(bb.GetY()) + 0.025, mm(bb.GetRight()) - 0.025, mm(bb.GetBottom()) - 0.025) if False else \
            (mm(edge[0].GetStart().x), mm(edge[0].GetStart().y), mm(edge[0].GetEnd().x), mm(edge[0].GetEnd().y))
    else:
        xs = [mm(d.GetStart().x) for d in edge] + [mm(d.GetEnd().x) for d in edge]
        ys = [mm(d.GetStart().y) for d in edge] + [mm(d.GetEnd().y) for d in edge]
        outline = (min(xs), min(ys), max(xs), max(ys))
    fps = {}
    for f in b.GetFootprints():
        pb = pcbnew.BOX2I()
        for p in f.Pads():
            pb.Merge(p.GetBoundingBox())
        cy = f.GetCourtyard(pcbnew.F_CrtYd)
        cb = cy.BBox() if cy.OutlineCount() else pb
        fps[f.GetReference()] = dict(
            pos=(mm(f.GetPosition().x), mm(f.GetPosition().y)),
            pads=(mm(pb.GetX()), mm(pb.GetY()), mm(pb.GetRight()), mm(pb.GetBottom())),
            cy=(mm(cb.GetX()), mm(cb.GetY()), mm(cb.GetRight()), mm(cb.GetBottom())),
            fp=f.GetFPIDAsString())
        fps[f.GetReference()]["pins"] = [(mm(p.GetPosition().x), mm(p.GetPosition().y), p.GetNumber(), p.GetNetname()) for p in f.Pads()]
    masks = []
    for z in b.Zones():
        if [b.GetLayerName(l) for l in z.GetLayerSet().Seq()] == ["B.Mask"]:
            bb = z.GetBoundingBox()
            masks.append((mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetRight()), mm(bb.GetBottom())))
    return dict(outline=outline, fps=fps, masks=masks, thick=mm(b.GetDesignSettings().GetBoardThickness()))


A = load(os.path.join(HW, "board-a", "DingoPDM.kicad_pcb"))
B = load(os.path.join(HW, "board-b-max", "dingoPDM-Max.kicad_pcb"))
IN = load(os.path.join(HW, "input-board", "input-board.kicad_pcb"))


def size(bd):
    o = bd["outline"]
    return o[2] - o[0], o[3] - o[1]


AW, AH = size(A)
BW, BH = size(B)
IW, IH = size(IN)

# ---- placement (plan coords: origin = inside NW corner of the box, X east, Y south) ---------------------------
place = {}
x = WEST
place["B"] = (x, NORTH); x += BW + GAP
place["A1"] = (x, NORTH); x += AW + GAP
place["A2"] = (x, NORTH); x += AW
BOX_W = x + EAST
ROW_Y = NORTH + max(AH, BH) + ROWGAP
for k, m in (("IN3", "B"), ("IN1", "A1"), ("IN2", "A2")):
    place[k] = (place[m][0] + 3.0, ROW_Y)
BOX_H = ROW_Y + IH + SOUTH


def to_plan(name, bd, pt):
    ox, oy = place[name]
    o = bd["outline"]
    return ox + pt[0] - o[0], oy + pt[1] - o[1]


# ---- SVG helpers --------------------------------------------------------------------------------------------
S = 2.6          # px per mm, overview
svg = []
add = svg.append


def R(x0, y0, x1, y1, s=S, ox=0.0, oy=0.0, **kw):
    a = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in kw.items())
    add(f'<rect x="{(x0) * s + ox:.1f}" y="{(y0) * s + oy:.1f}" width="{(x1 - x0) * s:.1f}" height="{(y1 - y0) * s:.1f}" {a}/>')


def T(x, y, txt, size=10, anchor="start", s=1.0, ox=0.0, oy=0.0, cls="t", **kw):
    a = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in kw.items())
    add(f'<text x="{x * s + ox:.1f}" y="{y * s + oy:.1f}" font-size="{size}" text-anchor="{anchor}" class="{cls}" {a}>{txt}</text>')


def C(x, y, r, s=S, ox=0.0, oy=0.0, **kw):
    a = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in kw.items())
    add(f'<circle cx="{x * s + ox:.1f}" cy="{y * s + oy:.1f}" r="{r * s:.1f}" {a}/>')


def L(pts, s=S, ox=0.0, oy=0.0, **kw):
    a = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in kw.items())
    p = " ".join(f"{x * s + ox:.1f},{y * s + oy:.1f}" for x, y in pts)
    add(f'<polyline points="{p}" fill="none" {a}/>')


MX, MY = 20.0, 70.0   # overview origin in px
PW = int(BOX_W * S + 2 * MX)
H1 = int(BOX_H * S + MY + 30)

# detail panels (bigger scale)
DS = 4.6
DY = H1 + 10
DAW = int(AW * DS + 40)
DBW = int(BW * DS + 40)
CANV_W = max(PW, DAW + DBW + 40)
CANV_H = int(DY + max(AH, BH) * DS + 150)

add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CANV_W} {CANV_H}" width="100%" font-family="Segoe UI, Arial, sans-serif">')
add("""<style>
:root{--bg:#ffffff;--fg:#1d2430;--mut:#5c6675;--wall:#8a94a3;--brd:#e6efe6;--brdl:#2f6f3a;--chip:#c0392b;--win:#f1c40f;--ped:#2e86c1;--wire:#d35400;--bar:#b7791f;--grid:#d9dee5;--in:#ede7f6;--inl:#5e35b1}
@media (prefers-color-scheme:dark){:root{--bg:#161a20;--fg:#e6e9ee;--mut:#9aa5b4;--wall:#6c7686;--brd:#22332a;--brdl:#5fb06c;--chip:#ef6a5b;--win:#f4d03f;--ped:#5dade2;--wire:#f0883e;--bar:#e0b04a;--grid:#2c333d;--in:#2a2438;--inl:#a58be0}}
.bg{fill:var(--bg)} .t{fill:var(--fg)} .m{fill:var(--mut)}
</style>""")
add(f'<rect class="bg" width="{CANV_W}" height="{CANV_H}"/>')
T(MX, 24, "custom-pdm enclosure layout - PROPOSAL (2D plan, top view)", 16, cls="t", font_weight="bold")
T(MX, 42, "ILLUSTRATION generated by tools/gen_enclosure_layout.py from the board files + TE / Wuerth data. Not approved, not a source of truth. Placement margins are assumptions (open questions).", 10, cls="m")
T(MX, 56, f"Inner plan about {BOX_W:.0f} x {BOX_H:.0f} mm (boards flat on one base plate / heat sink; heights not shown). North = top of the page = top of the board renders.", 10, cls="m")

# box
R(0, 0, BOX_W, BOX_H, ox=MX, oy=MY, fill="none", stroke="var(--wall)", stroke_width=3)
T(2, 5, "NORTH wall", 8, s=S, ox=MX, oy=MY, cls="m")
T(2, BOX_H - 2, "SOUTH wall", 8, s=S, ox=MX, oy=MY, cls="m")
T(1, BOX_H / 2, "WEST", 8, s=S, ox=MX, oy=MY, cls="m")


def board(name, bd, label, ins=False):
    ox, oy = place[name]
    o = bd["outline"]
    w, h = o[2] - o[0], o[3] - o[1]
    R(ox, oy, ox + w, oy + h, ox=MX, oy=MY, fill="var(--in)" if ins else "var(--brd)", stroke="var(--inl)" if ins else "var(--brdl)", stroke_width=1.6)
    T(ox + 2, oy + 5, label, 11, s=S, ox=MX, oy=MY, cls="t", font_weight="bold")


def item(name, bd, rect, fill, stroke, label=None, sw=1.0, dash=None, lsize=8):
    x0, y0 = to_plan(name, bd, (rect[0], rect[1]))
    x1, y1 = to_plan(name, bd, (rect[2], rect[3]))
    kw = dict(fill=fill, stroke=stroke, stroke_width=sw)
    if dash:
        kw["stroke_dasharray"] = dash
    R(x0, y0, x1, y1, ox=MX, oy=MY, **kw)
    if label:
        T((x0 + x1) / 2, (y0 + y1) / 2 + 2.5, label, lsize, "middle", s=S, ox=MX, oy=MY, cls="t")


# main boards
for nm, bd, lab in (("B", B, "B  (111.4 x 95.3)"), ("A1", A, "A1  (72.4 x 95.3)"), ("A2", A, "A2  (72.4 x 95.3)")):
    board(nm, bd, lab)
    fp = bd["fps"]
    if nm in ("A1", "A2"):
        j3 = fp["J3"]["pos"]
        item(nm, bd, (j3[0] - DT15_HALF[0], j3[1] - DT15_HALF[1], j3[0] + DT15_HALF[0], j3[1] + DT15_HALF[1]), "none", "var(--mut)", None, 1.0, "5 3")
        T(0, 0, "", 1)
        x0, y0 = to_plan(nm, bd, (j3[0], j3[1] - 8.5))
        T(x0, y0, "J3 DT15 housing", 7.5, "middle", s=S, ox=MX, oy=MY, cls="m")
        T(x0, y0 + 4, "59.2 x 35.3, 30.1 high", 7, "middle", s=S, ox=MX, oy=MY, cls="m")
        for ref in ("U8", "U10", "U11", "U13"):
            item(nm, bd, fp[ref]["pads"], "var(--chip)", "none", None)
        for m in bd["masks"]:
            item(nm, bd, m, "var(--win)", "none")
        for ref, lab2 in (("J1", "+12V"), ("J2", "GND")):
            item(nm, bd, fp[ref]["cy"], "none", "var(--bar)", lab2, 1.4, lsize=8)
        item(nm, bd, fp["J5"]["cy"], "none", "var(--mut)", "USB-C", 1.0, lsize=7)
    else:
        for ref in ("U8", "U9", "U10", "U11", "U23", "U24", "U25", "U26"):
            item(nm, bd, fp[ref]["pads"], "var(--chip)", "none", None)
        for m in bd["masks"]:
            item(nm, bd, m, "var(--win)", "none")
        for ref, lab2 in (("J1", "+12V"), ("J3", "GND")):
            item(nm, bd, fp[ref]["cy"], "none", "var(--bar)", lab2, 1.4, lsize=8)
        item(nm, bd, fp["J2"]["cy"], "none", "var(--mut)", "USB-C", 1.0, lsize=7)
        for t in ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"):
            item(nm, bd, fp[t]["cy"], "none", "var(--wire)", t, 1.2, lsize=8)
    # mounting holes
    for ref, f in fp.items():
        if ref.startswith("H") and ref[1:].isdigit():
            x0, y0 = to_plan(nm, bd, f["pos"])
            C(x0, y0, 1.6, ox=MX, oy=MY, fill="var(--bg)", stroke="var(--mut)", stroke_width=1)

# input boards
for nm, lab in (("IN3", "input #3 (66 x 64)"), ("IN1", "input #1"), ("IN2", "input #2")):
    board(nm, IN, lab, ins=True)
    for ref, lab2 in (("J1", "J1 GH"), ("J2", "J2 Micro-Fit")):
        item(nm, IN, IN["fps"][ref]["cy"], "none", "var(--inl)", lab2, 1.0, lsize=7)

# walls: X1, X2, studs
x1c = (place["A1"][0] + AW / 2 + 5, -8.0)
X1 = (place["A1"][0] + AW + GAP / 2, 14.0)          # x of X1 on the north wall
X2 = (place["IN1"][0] + IW / 2 + 40, BOX_H - 14.0)  # x of X2 on the south wall
DEPTH_X = 28.0   # inside part of a size-24 receptacle behind the wall: TE drawing HDP24-24-XXP/SX-L015 (overall 58.67, flange at 26.16 + 2.54); HD34 drawing TBD
for (cx, wy, up, lab) in ((X1[0], 0.0, +1, "X1 HD34-24-21SN"), (X2[0], BOX_H, -1, "X2 HDP24-24-47SE-L017")):
    y0, y1 = (wy, wy + DEPTH_X) if up > 0 else (wy - DEPTH_X, wy)
    R(cx - FLANGE_D / 2, y0, cx + FLANGE_D / 2, y1, ox=MX, oy=MY, fill="none", stroke="var(--wall)", stroke_width=2, stroke_dasharray="6 3")
    T(cx, (y0 + y1) / 2 + 1, lab, 9, "middle", s=S, ox=MX, oy=MY, cls="t")
    T(cx, (y0 + y1) / 2 + 7, "50.8 wide, ~28 inside (TBD)", 7.5, "middle", s=S, ox=MX, oy=MY, cls="m")
# OUT1-4 studs on the north wall (centres chosen over B's centre terminals), BATT / GND on the west wall
stud_pos = {}
bt = {t: to_plan("B", B, B["fps"][t]["pos"]) for t in ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8")}
jb1 = to_plan("B", B, B["fps"]["J1"]["pos"])    # +12V M6 terminal
jb3 = to_plan("B", B, B["fps"]["J3"]["pos"])    # GND M6 terminal
for i, k in enumerate(("OUT2", "OUT4", "OUT1", "OUT3")):     # left to right, same order as the terminals on board B
    stud_pos[k] = (place["B"][0] + 22.0 + i * (STUD_D + 3.0), 7.0)
stud_pos["GND"] = (7.0, jb3[1])
stud_pos["BATT"] = (7.0, jb1[1])
STUD_IN = 14.0   # drawn stud + nut depth inside the wall: TBD
for k, (cx, cy) in stud_pos.items():
    col = "var(--bar)" if k in ("GND", "BATT") else "var(--wire)"
    if k in ("GND", "BATT"):
        R(0, cy - STUD_D / 2, STUD_IN, cy + STUD_D / 2, ox=MX, oy=MY, fill="var(--bg)", stroke=col, stroke_width=2)
        T(STUD_IN / 2, cy + 1, k, 7.5, "middle", s=S, ox=MX, oy=MY, cls="t")
    else:
        R(cx - STUD_D / 2, 0, cx + STUD_D / 2, STUD_IN, ox=MX, oy=MY, fill="var(--bg)", stroke=col, stroke_width=2)
        T(cx, STUD_IN / 2 + 1, k, 7.5, "middle", s=S, ox=MX, oy=MY, cls="t")

# busbars: BATT along the +12V terminals of the three boards, GND along the GND terminals
for key, y_of, col in (("BATT", lambda nm, bd: to_plan(nm, bd, bd["fps"]["J1"]["pos"]), "BATT"), ("GND", None, "GND")):
    pts = []
    for nm, bd, ref in (("B", B, "J1" if key == "BATT" else "J3"), ("A1", A, "J1" if key == "BATT" else "J2"), ("A2", A, "J1" if key == "BATT" else "J2")):
        pts.append(to_plan(nm, bd, bd["fps"][ref]["pos"]))
    y = pts[0][1]
    L([(14.0, y), (pts[-1][0], y)], ox=MX, oy=MY, stroke="var(--bar)", stroke_width=7, stroke_opacity=0.55, stroke_linecap="round")
    for (px, py) in pts:
        C(px, py, 2.0, ox=MX, oy=MY, fill="var(--bar)", stroke="none")
T(1, jb1[1] + 14, "BATT bar", 7.5, s=S, ox=MX, oy=MY, cls="m")
T(1, jb3[1] + 14, "GND bar", 7.5, s=S, ox=MX, oy=MY, cls="m")

# wires
wire = dict(ox=MX, oy=MY, stroke="var(--wire)", stroke_width=1.6)
RUNS = {}
for i, t in enumerate(("T1", "T2", "T3", "T4")):
    px, py = bt[t]
    sx, sy = stud_pos[f"OUT{i + 1}"]
    dx = {"T1": -3.0, "T2": -3.0, "T3": 3.0, "T4": 3.0}[t]
    L([(px + dx, py), (px + dx, 24 + i * 2), (sx, 24 + i * 2), (sx, 14.0)], **wire)
    RUNS[f"{t} > OUT{i + 1} stud"] = abs(px + dx - sx) + abs(py - 14.0)
for t in ("T5", "T6", "T7", "T8"):
    px, py = bt[t]
    L([(px + 5, py), (place["B"][0] + BW + 3, py), (place["B"][0] + BW + 3, 30 + (int(t[1]) - 5) * 2), (X1[0] - 14 + (int(t[1]) - 5) * 3, 30 + (int(t[1]) - 5) * 2), (X1[0] - 14 + (int(t[1]) - 5) * 3, X1[1] + 4)], **wire)
for nm, bd in (("A1", A), ("A2", A)):
    jx, jy = to_plan(nm, bd, bd["fps"]["J3"]["pos"])
    L([(jx, jy - 8), (jx, 33 + (4 if nm == "A2" else 0)), (X1[0] + (-6 if nm == "A1" else 6), 33 + (4 if nm == "A2" else 0)), (X1[0] + (-6 if nm == "A1" else 6), X1[1] + 8)], ox=MX, oy=MY, stroke="var(--wire)", stroke_width=3.2)
# X2 signal runs from the input boards (J2) and CAN
for nm in ("IN3", "IN1", "IN2"):
    jx, jy = to_plan(nm, IN, IN["fps"]["J2"]["pos"])
    L([(jx - 9, jy), (jx - 12, jy), (jx - 12, BOX_H - 30), (X2[0] + (nm == "IN1") * 0 + (-10 if nm == "IN3" else (10 if nm == "IN2" else 0)), BOX_H - 30), (X2[0] + (-10 if nm == "IN3" else (10 if nm == "IN2" else 0)), X2[1] - 8)], ox=MX, oy=MY, stroke="var(--inl)", stroke_width=1.6)
# input board J1 (JST GH) -> board J6 / J7 cables (dotted)
for nm, mn, bd, ref in (("IN3", "B", B, "J7"), ("IN1", "A1", A, "J6"), ("IN2", "A2", A, "J6")):
    ax, ay = to_plan(nm, IN, IN["fps"]["J1"]["pos"])
    bx, by = to_plan(mn, bd, bd["fps"][ref]["pos"])
    L([(ax + 3, ay), (ax + 8, ay), (ax + 8, ROW_Y - 6), (bx, ROW_Y - 6), (bx, by + 10)], ox=MX, oy=MY, stroke="var(--inl)", stroke_width=1.2, stroke_dasharray="3 2")
T(place["IN1"][0], ROW_Y - 8, "JST GH cables (input board J1 > board J6 / J7)", 8, s=S, ox=MX, oy=MY - 2, cls="m")

# legend
lx, ly = MX, MY + BOX_H * S + 22
items = [("var(--chip)", "switch (pads)"), ("var(--win)", "bottom mask window (bare +12 V copper, gap pad)"), ("var(--bar)", "M6 terminal / bar / stud (BATT, GND)"), ("var(--wire)", "output wiring"), ("var(--inl)", "input / CAN / signal wiring")]
for i, (c, t) in enumerate(items):
    R(lx + i * 0, ly + i * 0, lx, ly, ox=0, oy=0, fill="none")
    add(f'<rect x="{lx + 0:.0f}" y="{ly - 9 + i * 0:.0f}" width="0" height="0"/>')
cx0 = lx
for c, t in items:
    add(f'<rect x="{cx0:.0f}" y="{ly - 9:.0f}" width="12" height="10" fill="{c}"/>')
    T(cx0 + 16, ly, t, 9, s=1.0, cls="t")
    cx0 += 16 + len(t) * 5.0 + 16

# ---- detail panels: heat path ----------------------------------------------------------------------------------
def detail(name, bd, ox, oy, title, pedestals, pocket=None, centre=None, housing=None):
    o = bd["outline"]
    w, h = o[2] - o[0], o[3] - o[1]
    T(ox, oy - 8, title, 11, cls="t", font_weight="bold")
    R(0, 0, w, h, s=DS, ox=ox, oy=oy, fill="var(--brd)", stroke="var(--brdl)", stroke_width=1.5)
    lp = lambda p: (p[0] - o[0], p[1] - o[1])
    def drect(r, **kw):
        a, b2 = lp((r[0], r[1])); c2, d = lp((r[2], r[3]))
        R(a, b2, c2, d, s=DS, ox=ox, oy=oy, **kw)
    fp = bd["fps"]
    if housing is not None:
        j3 = fp["J3"]["pos"]
        drect((j3[0] - DT15_HALF[0], j3[1] - DT15_HALF[1], j3[0] + DT15_HALF[0], j3[1] + DT15_HALF[1]), fill="none", stroke="var(--mut)", stroke_width=1, stroke_dasharray="5 3")
        for (xa, xb) in DT15_FEET:
            for sg in (1, -1):
                ya, yb = sorted((sg * DT15_FOOT_Y[0], sg * DT15_FOOT_Y[1]))
                drect((j3[0] + xa, j3[1] + ya, j3[0] + xb, j3[1] + yb), fill="var(--mut)", fill_opacity=0.25, stroke="var(--mut)", stroke_width=0.8)
    for p in pedestals:
        drect(p, fill="var(--ped)", fill_opacity=0.28, stroke="var(--ped)", stroke_width=1.6, stroke_dasharray="6 3")
    if pocket:
        drect(pocket, fill="none", stroke="var(--wire)", stroke_width=1.6, stroke_dasharray="2 2")
    for ref, f in fp.items():
        if ref in ("U8", "U9", "U10", "U11", "U13", "U23", "U24", "U25", "U26") and ref in bd["_chips"]:
            drect(f["pads"], fill="var(--chip)", stroke="none")
            a, b2 = lp(((f["pads"][0] + f["pads"][2]) / 2, f["pads"][1] - 1.2))
            T(a, b2, ref, 8, "middle", s=DS, ox=ox, oy=oy, cls="t")
    for m in bd["masks"]:
        drect(m, fill="var(--win)", stroke="none")
    for ref, f in fp.items():
        if ref.startswith("H") and ref[1:].isdigit():
            a, b2 = lp(f["pos"])
            C(a, b2, 1.6, s=DS, ox=ox, oy=oy, fill="var(--bg)", stroke="var(--mut)", stroke_width=1)
    if housing is not None:
        for (px, py, num, net) in fp["J3"]["pins"]:
            a, b2 = lp((px, py))
            C(a, b2, 1.3, s=DS, ox=ox, oy=oy, fill="var(--wire)", stroke="none")
    if centre:
        a, b2 = lp(centre)
        C(a, b2, 2.0, s=DS, ox=ox, oy=oy, fill="none", stroke="var(--ped)", stroke_width=2)
        T(a + 3, b2 - 2.5, "centre standoff?", 8, s=DS, ox=ox, oy=oy, cls="t")


A["_chips"] = ("U8", "U10", "U11", "U13")
B["_chips"] = ("U8", "U9", "U10", "U11", "U23", "U24", "U25", "U26")
PM = 1.5   # pedestal margin around the windows (assumption)
# board A pedestals: two, each covers the two windows of a chip pair + margin; pocket = J3 pad box
amasks = sorted(A["masks"], key=lambda m: (m[1], m[0]))
south = [m for m in amasks if m[1] > 0 and m[0] > -5]       # U11 + U8 windows (drop the leftover window at the old U9 spot)
north = [m for m in amasks if m[1] < 0]
def hull(ms, pm):
    return (min(m[0] for m in ms) - pm, min(m[1] for m in ms) - pm, max(m[2] for m in ms) + pm, max(m[3] for m in ms) + pm)
a_ped = [hull(south, PM), hull(north, PM)]
j3p = A["fps"]["J3"]["pads"]
a_pocket = (j3p[0] - 1.0, j3p[1] - 1.0, j3p[2] + 1.0, j3p[3] + 1.0)
a_centre = ((a_ped[0][0] + a_ped[0][2]) / 2, 0.05)
detail("A", A, 20, DY + 30, "Board A heat path (top view)", a_ped, a_pocket, a_centre, housing=True)
# leftover mask window at the old U9 spot
lm = [m for m in amasks if m[0] < -5][0]
a0 = A["outline"]
add(f'<text class="t" font-size="8" x="{20 + (lm[0] - a0[0]) * DS:.0f}" y="{DY + 30 + (lm[3] - a0[1]) * DS + 11:.0f}">old U9 window</text>')
# board B pedestals: two pairs (BTS70012) + one rail (BTS7004 column)
bm = B["masks"]
b70012 = [m for m in bm if (m[2] - m[0]) > 5]
b7004 = [m for m in bm if (m[2] - m[0]) <= 5]
bs = [m for m in b70012 if m[1] > 0]
bn = [m for m in b70012 if m[1] < 0]
b_ped = [hull(bs, PM), hull(bn, PM), hull(b7004, PM)]
detail("B", B, 20 + DAW + 20, DY + 30, "Board B heat path (top view)", b_ped)
T(20, DY + 30 + AH * DS + 22, "Pedestal margin 1.5 mm and rail width are placeholders. Blue dashed = proposed heat-sink pedestals, yellow = bottom mask windows (bare +12 V copper), red = switch pads,", 9, cls="m")
T(20, DY + 30 + AH * DS + 36, "orange dots / dotted box = J3 pin tails and the sink pocket, grey dashed = DT15 housing envelope with its four feet. Insulating gap pad goes between each window and its pedestal.", 9, cls="m")
add("</svg>")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w", encoding="utf-8").write("\n".join(svg))

# ---- numbers for docs/enclosure-layout.md ---------------------------------------------------------------------
print(f"board A {AW:.2f} x {AH:.2f}  board B {BW:.2f} x {BH:.2f}  input {IW:.2f} x {IH:.2f}  thickness A {A['thick']:.2f} mm")
print(f"placement (box inner coords): " + ", ".join(f"{k} at ({v[0]:.1f}, {v[1]:.1f})" for k, v in place.items()))
print(f"BOX inner plan {BOX_W:.1f} x {BOX_H:.1f} mm  (main row {ROW_Y - ROWGAP - NORTH:.1f} deep)")
print("A pedestals:", [tuple(round(v, 1) for v in p) for p in a_ped], "pocket", tuple(round(v, 1) for v in a_pocket), "centre", tuple(round(v, 2) for v in a_centre))
print("B pedestals:", [tuple(round(v, 1) for v in p) for p in b_ped])
for p in a_ped + b_ped:
    print("  ped size %.1f x %.1f = %.0f mm2" % (p[2] - p[0], p[3] - p[1], (p[2] - p[0]) * (p[3] - p[1])))
print("A mask windows:", [tuple(round(v, 2) for v in m) for m in A["masks"]])
print("B mask windows:", [tuple(round(v, 2) for v in m) for m in B["masks"]])
print("BATT stud", tuple(round(v, 1) for v in stud_pos["BATT"]), "GND stud", tuple(round(v, 1) for v in stud_pos["GND"]))
print("M6 terminals (plan): B +12V %.1f,%.1f  GND %.1f,%.1f" % (jb1[0], jb1[1], jb3[0], jb3[1]))
for nm in ("A1", "A2"):
    print(nm, "J1", tuple(round(v, 1) for v in to_plan(nm, A, A["fps"]["J1"]["pos"])), "J2", tuple(round(v, 1) for v in to_plan(nm, A, A["fps"]["J2"]["pos"])), "J3", tuple(round(v, 1) for v in to_plan(nm, A, A["fps"]["J3"]["pos"])))
for k, v in RUNS.items():
    print("plan run (Manhattan, no height):", k, round(v))
x1_rear = (X1[0], DEPTH_X)
for nm in ("A1", "A2"):
    jx, jy = to_plan(nm, A, A["fps"]["J3"]["pos"])
    print("plan run", nm, "J3 > X1 rear:", round(abs(jx - x1_rear[0]) + abs(jy - x1_rear[1])))
for t in ("T5", "T6", "T7", "T8"):
    print("plan run B", t, "> X1 rear:", round(abs(bt[t][0] - x1_rear[0]) + abs(bt[t][1] - x1_rear[1])), " at", tuple(round(v, 1) for v in bt[t]))
print("X1 x", round(X1[0], 1), "X2 x", round(X2[0], 1), "bar lengths BATT/GND (stud inner end to A2 terminal):", round(to_plan("A2", A, A["fps"]["J1"]["pos"])[0] - 14.0), round(to_plan("A2", A, A["fps"]["J2"]["pos"])[0] - 14.0))
print("wrote", OUT)
