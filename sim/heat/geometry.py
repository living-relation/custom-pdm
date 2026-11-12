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
    """fin boxes (x0, x1, y0, y1); pack build_test2.py fin loop"""
    out, y = [], LY0 + FIN_EDGE
    while y + FIN_T <= LY1 - FIN_EDGE + 1e-6:
        near_foot = any(y < fy + FOOT_D / 2 + 2 and y + FIN_T > fy - FOOT_D / 2 - 2 for fy in (LY0 + 12, LY1 - 12))
        xe = LX1 - 12 - FOOT_D / 2 - 2 if near_foot else LX1 - FIN_EDGE
        out.append((LX0 + FIN_EDGE + 16, xe, y, y + FIN_T))
        y += FIN_PITCH
    return out
