"""Shared geometry and load data for the steady heat model (docs/heat-analysis.md).

World frame = Grok TEST 2 pack frame (handoff/HANDOFF.md S1): X east, Y north, Z up, mm.
Z = 0 is the sink field (plate top between pedestals). Variant b sink (no J3 pocket).
Board KiCad (x, y) -> world X = X0 + x + 37.846, Y = -(y + 33.274).
"""
# ---- stack (TEST 2 pack, build_test2.py P dict; all ASSUMED there) ----
PLATE_T = 8.0          # sink base plate
PED_H = 3.0            # pedestal height above the field
PAD_T = 1.0            # gap pad thickness (product TBD)
T_PCB = 1.769872       # board thickness (KiCad board setup)
Z_BOT = PED_H + PAD_T  # board bottom 4.0
Z_TOP = Z_BOT + T_PCB  # board top 5.77
FIN_H, FIN_T, FIN_PITCH, FIN_EDGE = 30.0, 2.0, 6.0, 10.0
FOOT_D = 16.0

# board placement (pack: 2.0 mm gaps)
X0 = {"B": 0.0, "A1": 111.39 + 2.0}
X0["A2"] = X0["A1"] + 72.39 + 2.0
BOARD_W = {"B": 111.39, "A1": 72.39, "A2": 72.39}
BOARD_D = 95.25

# sink footprint, variant b (pack HANDOFF 4: 280.2 x 119.25; lid_footprint())
LX0, LX1 = -10.0, X0["A2"] + 72.39 + 10.0
LY1 = 10.0
LY0 = LY1 - 119.25
# enclosure v2b (docs/enclosure-v2b.md): HEAT_GEOM=v2b-F1 / v2b-F2 -> deeper sink (front side at Y -130),
# F1 fins stop at the 18 mm east fan bay; F2 = straight-fin field of the same wetted area as the swept radial
# fins (equivalent-area model, convection.py scales nothing further). Default (unset) = Grok TEST 2 b as before.
import os as _os
HEAT_GEOM = _os.environ.get("HEAT_GEOM", "")
if HEAT_GEOM.startswith("v2b") or HEAT_GEOM == "revF":
    LY0 = -130.0
# revF = enclosure v2c F1 rev F (models folder custom-pdm-enclosure-revF, source enclosure/v2c/src/build_v2c.py P / sink
# section): pedestals 3.14, Bergquist TGP 3000 1.016 mm pad squeezed 15 % to 0.86 (board bottom still Z 4.0); fins stop at
# the 6 mm fan wall (fins end at LX1 - 27) and are cut back by the four foot keep-outs; aluminium M3 board bosses (dia 6,
# Z 0 to the board bottom) under H1-H4 (+ H5 / H6 on B); 2 x Sunon fans PUSH west from the east bay (air enters at the
# east end at cabin temperature).
if HEAT_GEOM == "revF":
    PED_H = 3.14
    PAD_T = 0.86
    Z_BOT = PED_H + PAD_T
    Z_TOP = Z_BOT + T_PCB
HOLES_AB = {"H1": (-33.02, 21.59), "H2": (26.67, -21.59), "H3": (-21.082, -21.59), "H4": (26.67, 21.59)}
HOLES_B = {"H5": (69.044, -10.684), "H6": (69.044, 35.896)}
BOSS_D = 6.0


def bosses():
    """(X, Y) world centres of the board-mount bosses (revF only; build_v2c.py BOSS)."""
    if HEAT_GEOM != "revF":
        return []
    out = []
    for n in ("B", "A1", "A2"):
        hs = dict(HOLES_AB)
        hs.update(HOLES_B if n == "B" else {})
        out += [W(n, x, y) for (x, y) in hs.values()]
    return out


def fin_span():
    """(x west, x east) of the fin field: the air-temperature ramp of the fan case runs over it"""
    f = fins()
    return min(a[0] for a in f), max(a[1] for a in f)


# revF: the fans push west (build_v2c.py F1: fan bay at the east end, "push west"): the air enters at the east end
AIR_IN_EAST = HEAT_GEOM == "revF"


def W(n, xk, yk):
    return (X0[n] + xk + 37.846, -(yk + 33.274))


# pedestals = bottom-mask window hull + 1.5 mm (pack PED dict, repo doc 4.2), KiCad coords
PED = {"A": [(-1.905, 13.132, 11.379, 14.021), (-1.981, 10.922, -13.970, -11.227)],
       "B": [(-12.22, 12.32, 11.15, 14.07), (-12.22, 12.32, -14.07, -11.15),
             (53.623, 56.265, -27.415, 46.417)]}
PED_MARGIN = 1.5

# driver chips: exposed-pad (EP) centre and size in KiCad axes, read from the board files
# (EP pad of each footprint); vias = 0.8/0.4 mm vias inside the EP outline
A_CHIPS = [("U8", 11.145, 12.700), ("U11", 0.082, 12.700), ("U10", 8.960, -12.553), ("U13", 0.010, -12.654)]
B_70012 = [("U8", 9.100, 12.588), ("U9", -8.985, 12.690), ("U10", 8.997, -12.609), ("U11", -9.011, -12.558)]
B_7004 = [("U23", 54.944, -25.439), ("U24", 54.944, -2.149), ("U25", 54.944, 21.141), ("U26", 54.944, 44.431)]
EP = {"BTS7008": (4.00, 2.65, 12), "BTS70012": (6.40, 2.77, 9), "BTS7004": (2.65, 4.00, 12)}

# losses per chip, W (docs/enclosure-layout.md 4.3)
LOSS = {"worst": {"BTS7008": 1.80, "BTS70012": 2.37, "BTS7004": 1.80},
        "typical": {"BTS7008": 4.05 / 4, "BTS70012": 5.38 / 4, "BTS7004": 3.96 / 4}}
# junction-to-case (exposed pad) max, K/W, Infineon datasheets Table 6
RTHJC_MAX = {"BTS7008": 1.4, "BTS70012": 0.7, "BTS7004": 2.4}
TJ_MAX = 150.0


def chips():
    """list of dicts: id, type, board, world rect (x0, x1, y0, y1), vias"""
    out = []
    for n in ("B", "A1", "A2"):
        lst = [(r, x, y, "BTS7008") for r, x, y in A_CHIPS] if n != "B" else \
              [(r, x, y, "BTS70012") for r, x, y in B_70012] + [(r, x, y, "BTS7004") for r, x, y in B_7004]
        for r, x, y, t in lst:
            wx, wy, nv = EP[t]
            (xa, ya), (xb, yb) = W(n, x - wx / 2, y - wy / 2), W(n, x + wx / 2, y + wy / 2)
            out.append(dict(id=f"{n}-{r}", type=t, board=n, vias=nv,
                            rect=(min(xa, xb), max(xa, xb), min(ya, yb), max(ya, yb))))
    return out


def pedestals():
    out = []
    for n in ("B", "A1", "A2"):
        for (a, b, c, d) in PED["B" if n == "B" else "A"]:
            (xa, ya), (xb, yb) = W(n, a - PED_MARGIN, c - PED_MARGIN), W(n, b + PED_MARGIN, d + PED_MARGIN)
            out.append((min(xa, xb), max(xa, xb), min(ya, yb), max(ya, yb)))
    return out


def fins():
    """fin boxes (x0, x1, y0, y1); pack build_test2.py fin loop (v2b-F1: east fan bay; v2b-F2: equivalent area)"""
    if HEAT_GEOM == "revF":
        # build_v2c.py: fins from LX0 + fe + 16 to bay_x0 + 1 = LX1 - fe - 17, cut by the foot keep-outs
        # (X - 15 sx .. X + sx (web_L + 3), same in y, feet at LX0 / LX1 -+ 14, LY0 / LY1 -+ 14)
        out, y = [], LY0 + FIN_EDGE
        xa, xb = LX0 + FIN_EDGE + 16, LX1 - FIN_EDGE - 17
        keep = []
        for (X, Y, sx, sy) in ((LX0 + 14, LY0 + 14, 1, 1), (LX0 + 14, LY1 - 14, 1, -1), (LX1 - 14, LY0 + 14, -1, 1),
                               (LX1 - 14, LY1 - 14, -1, -1)):
            keep.append((min(X - 15 * sx, X + sx * 23), max(X - 15 * sx, X + sx * 23),
                         min(Y - 15 * sy, Y + sy * 23), max(Y - 15 * sy, Y + sy * 23)))
        while y + FIN_T <= LY1 - FIN_EDGE + 1e-6:
            x0, x1 = xa, xb
            for (k0, k1, k2, k3) in keep:
                if y < k3 and y + FIN_T > k2:
                    if k0 <= x0 < k1:
                        x0 = k1
                    if k0 < x1 <= k1:
                        x1 = k0
            out.append((x0, x1, y, y + FIN_T))
            y += FIN_PITCH
        return out
    if HEAT_GEOM in ("v2b-F1", "v2b-F2"):
        out, y = [], LY0 + FIN_EDGE
        xe = LX1 - FIN_EDGE - 18.0
        if HEAT_GEOM == "v2b-F2":
            L_TOT = float(_os.environ.get("F2_FIN_LEN_MM", "4000"))   # total swept-fin length from the CAD (build meta)
            n = int(round((LY1 - LY0 - 2 * FIN_EDGE) / FIN_PITCH)) + 1
            xe = LX0 + FIN_EDGE + 16 + L_TOT / n
        while y + FIN_T <= LY1 - FIN_EDGE + 1e-6:
            out.append((LX0 + FIN_EDGE + 16, min(xe, LX1 - FIN_EDGE), y, y + FIN_T)); y += FIN_PITCH
        return out
    out, y = [], LY0 + FIN_EDGE
    while y + FIN_T <= LY1 - FIN_EDGE + 1e-6:
        near_foot = any(y < fy + FOOT_D / 2 + 2 and y + FIN_T > fy - FOOT_D / 2 - 2 for fy in (LY0 + 12, LY1 - 12))
        xe = LX1 - 12 - FOOT_D / 2 - 2 if near_foot else LX1 - FIN_EDGE
        out.append((LX0 + FIN_EDGE + 16, xe, y, y + FIN_T))
        y += FIN_PITCH
    return out
