"""custom-pdm enclosure v2c revE: ONE path table for the inside-the-box harness (CPDM-HAR-200).
For every row of harness/enclosure-wire-list.csv (the master) a 3-D polyline from its From end to its To end, the wire OD and its
colour. build_v2c.py sweeps the STEP solids from it, fusion_v2c.py builds the same wires in Fusion from the JSON it writes
(<run>/<VAR>/harness_paths.json), and `lengths` writes the modelled lengths back into the CSV.
World frame = build_v2c.py (X east, Y north, Z up, mm).

Ends (sources):
  board A J3 / J6, board B J6 / J7 / T5-T8, input board J1 / J2: footprint and pad positions read from the .kicad_pcb files (main,
    2026-11-21: A J3 pads +/-11.11 / 6.67 / 2.22 at y -/+4.56; A J6 pads x -30.55; B J6 +/-1.5; B J7 (38.294, 44.6); input board
    J1 (60, 24) / J2 (10, 24)), placed with build_v2c.py W() / the input-board placement.
  X1 / X2: rear face = the placed TE model's rear (meta REAR). The TE customer-view models have NO cavities, so the cavity
    positions inside the rear face are a generated ring pattern (ASSUMED, not the TE insert arrangement: X1 13 on r 15, 7 on r 7.5,
    1 centre; X2 20 / 14 / 9 / 4 on r 15 / 11 / 7 / 3, counter-clockwise from the top seen from inside the box). Length error <= 2 x r.
  Micro-Fit 43025 / JST GHR housings, USB plugs, splices and the T5-T8 ring lugs are not modelled: wires end at the ASSUMED wire
    exit of the housing (Micro-Fit 9.0 behind the header face, rows 2.82 / 5.82 above the board; GH 5.4 from the pad row) or at the
    lug barrel end (Phoenix 3240083: 14 from the ring centre).
OD: enclosure_harness.py WP (GXL16 2.80, GXL12 3.65, M22759/16-20 1.52); ASSUMED where WP has none: 28 AWG 0.90 (JST GH
  SSHL-002T-P0.2 takes insulation OD 0.76-1.00; UL1571 28 AWG is about 0.9), USB cable 4.0 (revD value, cable part TBD).
USB: one round cable per cable U1-U4 (its cores W095-W111 are the CSV rows). U1 keeps the revD route (y -95 lane, then down to
  the hub); U3 / U4 run side by side south of the board edge; U2 is a short piece over the hub (no plug fits between the hub and
  board B's USB-C: open problem). The USB-C plugs are not modelled.
Bend radius: every wire is filleted at 3 x OD (centre line); a wire whose points do not leave room fails the build. Cable U1's
  revD route has legs shorter than 3 x OD = 12 allows: it is built as cylinders + spheres and its smallest radius is reported.
Wire against wire: the routes keep each flat group in order (no crossing inside a ribbon), but the fan-outs behind X1 / X2 and
  the places where two groups cross are NOT untangled: wirecheck_v2c.py lists those wire-wire overlaps (they do not fail).
Usage: python harness_paths_v2c.py table <meta.json> <out.json> | lengths <harness_paths.json> [--write]
"""
import os, sys, csv, json, math

RGB = {"RD": (0.80, 0.10, 0.10), "WH": (0.92, 0.92, 0.88), "VT": (0.50, 0.20, 0.70), "BK": (0.08, 0.08, 0.08), "YE": (0.95, 0.80, 0.10),
       "GN": (0.10, 0.60, 0.20), "GY": (0.50, 0.50, 0.50)}
OD_28AWG = 0.90; OD_USB = 4.0; CABLE_RGB = (0.12, 0.12, 0.14)
SERVICE_LOOP = 2 * 15.0                         # circuit-list.md length rule: model route + 2 x 15 mm service loop, up to 5 mm (the old + 20 mm X1 / X2 fan-out is in the model now)
def wt_root(): return os.environ.get("WT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
def csv_path(): return os.path.join(wt_root(), "harness", "enclosure-wire-list.csv")
def read_rows():
    with open(csv_path(), newline="", encoding="utf-8") as fh: return list(csv.DictReader(fh))
def wire_od(pn):
    sys.path.insert(0, os.path.join(wt_root(), "harness", "src"))
    import enclosure_harness as EH
    k = EH.PN2WP.get(pn); od = EH.WP[k][4] if k else None
    return (od, "enclosure_harness.py WP") if od else (OD_28AWG, "ASSUMED 28 AWG")

# ---------------- geometry helpers ----------------
def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def add(a, b, s=1.0): return (a[0] + b[0] * s, a[1] + b[1] * s, a[2] + b[2] * s)
def dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def norm(a): return math.sqrt(dot(a, a))
def unit(a): n = norm(a); return (a[0] / n, a[1] / n, a[2] / n)
def rounded(pts, R):
    """polyline -> [("L", p0, p1) | ("A", p0, p1, mid, centre, r)], length, smallest arc radius. Each inner vertex is filleted at R;
    where the neighbouring legs are too short the radius shrinks to what fits (the caller decides whether that is allowed)."""
    pts = [tuple(float(c) for c in p) for p in pts]
    pts = [p for i, p in enumerate(pts) if i == 0 or norm(sub(p, pts[i - 1])) > 1e-6]
    n = len(pts); Ls = [norm(sub(pts[i + 1], pts[i])) for i in range(n - 1)]
    segs = []; cur = pts[0]; rmin = 1e9; total = 0.0
    TH = [0.0] * n
    for i in range(1, n - 1):
        TH[i] = math.acos(max(-1.0, min(1.0, dot(unit(sub(pts[i], pts[i - 1])), unit(sub(pts[i + 1], pts[i]))))))
    TN = [R * math.tan(a / 2) for a in TH]                           # tangent length each vertex needs; a leg shared by two bends that do not fit scales both
    F = [1.0] * n
    for j in range(n - 1):
        s = TN[j] + TN[j + 1]
        if s > Ls[j]: F[j] = min(F[j], Ls[j] / s); F[j + 1] = min(F[j + 1], Ls[j] / s)
    for i in range(1, n - 1):
        u = unit(sub(pts[i], pts[i - 1])); v = unit(sub(pts[i + 1], pts[i])); th = TH[i]
        if th < 1e-4: continue
        r = R * F[i]; t = r * math.tan(th / 2); rmin = min(rmin, r)
        p1 = add(pts[i], u, -t); p2 = add(pts[i], v, t); w = unit(sub(v, u)); c = add(pts[i], w, r / math.cos(th / 2)); mid = add(c, w, -r)
        if norm(sub(p1, cur)) > 1e-5: segs.append(("L", cur, p1)); total += norm(sub(p1, cur))
        else: p1 = cur                                               # two bends meet: snap, no zero-length edge
        segs.append(("A", p1, p2, mid, c, r)); total += r * th; cur = p2
    if norm(sub(pts[-1], cur)) > 1e-5: segs.append(("L", cur, pts[-1])); total += norm(sub(pts[-1], cur))
    else: segs[-1] = segs[-1][:2] + (pts[-1],) + segs[-1][3:]
    return segs, total, rmin

# ---------------- the routes ----------------
PX = {1: -11.11, 2: -6.67, 3: -2.22, 4: 2.22, 5: 6.67, 6: 11.11, 7: 11.11, 8: 6.67, 9: 2.22, 10: -2.22, 11: -6.67, 12: -11.11}   # board A J3 pads (KiCad x)
X1_OUT = "A B C D E F G H J K L M N".split(); X1_IN = "P R S T U V W".split()
X2_RINGS = [(20, 15.0), (14, 11.0), (9, 7.0), (4, 3.0)]
A2_LANE = {8: (-104.9, 12.6), 9: (-102.0, 12.6), 10: (-99.1, 12.6), 6: (-104.9, 15.4), 5: (-102.0, 15.4), 4: (-99.1, 15.4), 3: (-96.2, 15.4)}   # low trunk under the X2 wires (lowest X2 cavity z 18), over USB cable U4
A2_ZTR = {"U": 24.5, "V": 27.3, "S": 30.1, "X": 32.9, "W": 35.7, "C": 38.5, "A": 41.3}   # A2 wires run west behind X1 in one plane, 2.8 apart in z, each near its cavity height
def table(G):
    ZT = G["Z_TOP"]; X0 = G["X0"]; CONN = G["CONN"]; TZ = G["TZ"]; Y1 = G["REAR"]["X1"]; Y2 = G["REAR"]["X2"]; IN_X = G["IN_X"]
    ZI = G["Z_IN"] + 1.51; GX, GY = G["GLAND"]; hb = G["HUB"]; T58 = G["T58"]
    def Wb(n, xk, yk): return (X0[n] + xk + 37.846, -(yk + 33.274))
    def j3(n, p):
        x, y = Wb(n, PX[p], -4.56 if p <= 6 else 4.56); return x, y, (17.2 if p <= 6 else 14.4)   # lane height: north row over south row
    def x1(c):
        if c == "X": return CONN["X1"], TZ
        a, r = (90 + X1_OUT.index(c) * 360 / 13, 15.0) if c in X1_OUT else (90 + X1_IN.index(c) * 360 / 7, 7.5)
        return CONN["X1"] + r * math.cos(math.radians(a)), TZ + r * math.sin(math.radians(a))
    def x2(k):
        k = int(k) - 1
        for n, r in X2_RINGS:
            if k < n: a = 90 + k * 360 / n; return CONN["X2"] + r * math.cos(math.radians(a)), TZ + r * math.sin(math.radians(a))
            k -= n
    def x2s(k): xc, zc = x2(k); return [(xc, Y2, zc), (xc, Y2 + 6.0, zc)]            # cavity + straight stub, outward
    def inj2(n, p): return IN_X[n] + 24.0 - 3.0 * ((p - 1) % 6), ZI + (2.82 if p <= 6 else 5.82)
    SPX = 170.0; SP = {"SP1": -90.0, "SP2": -87.0}; SPZ = 36.0                        # CAN splices: axis along x, 2 wires per side
    R = {}
    def a_pad(n, p): x, y, z = j3(n, p); return [(x, y, ZT), (x, y, z)]
    def a_x1(n, p, c):                                                              # board A J3 pad -> X1 (16 AWG)
        x, y, z = j3(n, p); xc, zc = x1(c); pts = a_pad(n, p)
        if n == "A1":
            pts += [(x, -80.0, z), (xc + 11.0, -90.5, z + 0.3 * (zc - z)), (xc, Y1 + 10.53, zc)] if zc < 30 else [(x, -76.0, z), (xc + 11.0, -90.5, 33.5), (xc, Y1 + 10.53, zc)]   # under / over USB cable U1 (y -95, z 27-30)
        else:
            yl, zl = A2_LANE[p]; ya = -101.9; ztr = A2_ZTR[c]
            pts += [(x, yl, z), (212.0, yl, z), (204.0, yl, zl), (158.0, yl, zl)] + ([(150.0, -100.5, zl)] if yl > -97 else []) + [(xc + 14.0, ya, ztr), (xc, ya, ztr)]
        return pts + [(xc, Y1, zc)]
    def t_x1(k, c):                                                                 # board B T5-T8 lug barrel end -> X1 (12 AWG)
        X, Y = T58[k]; zb = G["TTOP"] + 2.8; xc, zc = x1(c)
        if k == "T8": return [(X, Y - 14.0, zb), (X, Y - 18.0, zb), (xc, Y1 + 4.83, zc), (xc, Y1, zc)]
        e = {"T7": 0.0, "T6": 7.4, "T5": 14.8}[k]; u = (-0.5, -math.sqrt(3) / 2)
        A = (X + 14 * u[0], Y + 14 * u[1], zb); bx, by = X + (17.43 + e) * u[0], Y + (17.43 + e) * u[1]
        pts = [A, (bx, by, zb), (bx, by - 8.0, zb), (bx, by - 22.0, 16.6)]
        if k == "T7": pts += [(xc, Y1 + 6.83, zc)]
        if k == "T6": pts += [(92.5, -86.0, 28.0), (xc, -92.6, zc)]
        if k == "T5": pts += [(bx, -82.0, 16.6), (89.0, -92.5, 40.0), (xc, -101.5, zc)]              # up on the west side, then over the T6 wire
        return pts + [(xc, Y1, zc)]
    def a_low(n, p, y1, z1):                                                        # lane end of a 20 AWG wire on a board A pad, pad first
        x, y, z = j3(n, p); return a_pad(n, p) + [(x, y1 + 6.0, z), (x, y1, z1)]
    def bj6(p):                                                                     # board B J6 pad -> east end of the low trunk
        px = X0["B"] + 37.846 + (-1.5 if p in (1, 3) else 1.5); py = -(33.274 + (-1.5 if p <= 2 else 1.5)); zl = 12.12 if p <= 2 else 10.6
        xs = px if p in (1, 3) else 37.85; yt = -110.52 if p in (1, 3) else -109.0; zt = 9.42 if p <= 2 else 7.9
        return [(px, py, ZT), (px, py, zl)] + ([] if xs == px else [(px, py - 6.0, zl), (xs, py - 9.5, zl)]) + [(xs, -105.6, zl), (xs + 8.0, yt, zt), (150.0, yt, zt)], yt, zt   # stays above USB cables U3 / U4 (y -99.7 / -103.5), then down to the low trunk
    def gh(n, p, rank):                                                             # board GH connector -> input board J1 (28 AWG)
        z1 = ZI + 1.0
        if n == "B":
            # B J7 (vertical GH under the input deck): west, south out from under the deck, up beside the deck's south edge (east of the
            # lid's terrace wall, west of the Micro-Fit wires), north over input board 3 at z 48.1 (Micro-Fit header top 47.54), down
            # behind the board's north edge and back south into J1. The flat 12-wire order never crosses.
            y = -84.749 + 1.25 * (p - 1); xc = 70.7 - 0.92 * (p - 1); xi = IN_X["IN3"] + 30.875 - 1.25 * (p - 1)
            return [(76.144, y, ZT + 6.3), (76.144, y, 15.5), (xc, y - 0.5 * (76.144 - xc), 15.5), (xc + 1.0, -92.3, 15.5), (xc + 1.0, -92.3, 48.1), (xc + 1.0, -86.0, 48.1), (xi, -62.0, 48.1),
                    (xi, -13.3, 48.1), (xi, -13.3, z1), (xi, -16.5, z1)]
        y = -24.899 - 1.25 * (p - 1); xr = X0[n] - 1.0
        xk = {"A1": 127.5, "A2": 232.5}[n] + 0.95 * rank; yn = -1.9 - 0.95 * rank if n == "A1" else -9.5 + 0.95 * rank   # A2: risers east of J1 (the GND M6 head sits west of it)
        xi = IN_X["IN1" if n == "A1" else "IN2"] + 30.875 - 1.25 * (p - 1)
        return [(X0[n] + 1.9, y, ZT + 1.0), (xr, y, ZT + 1.0), (xr, y, 26.5), (xk, y, 26.5), (xk, yn, 26.5), (xk, yn, z1), (xi, yn, z1), (xi, -16.5, z1)]
    def fan(f, plus):                                                               # fan lead: fan retainer corner -> through the cord grip -> splice
        fy = G["FAN"]["y"][f]; xl = sum(G["FAN"]["x"]) / 2 + (-0.5 if plus else 0.5); zb = G["FAN"]["z"] - 15.0; zr = -41.5 if f == 0 else -42.6
        gx = GX + (-0.48 if plus else 0.48); gy = GY + (-0.48 if f == 0 else 0.48)
        return [(xl, fy - 12.0, zb), (xl, fy - 12.0, zr), (xl, -95.0, zr), (gx, gy, -33.0), (gx, gy, 18.0)]
    rows = read_rows(); ghrank = {}
    for r in rows:
        w = r["Wire ID"]; fc, fp, tc, tp = r["From connector"], r["From pin"], r["To connector"], r["To pin"]; pts = None; rev = False
        ends = {fc: fp, tc: tp}
        def has(*c): return all(k in ends for k in c)
        if r["Signal group"].startswith("C11"): continue                           # USB cores: one cable solid per cable, below
        brd = next((k[:2] for k in ends if k in ("A1-J3", "A2-J3")), None)
        if brd and "X1" in ends: pts = a_x1(brd, int(ends[brd + "-J3"]), ends["X1"]); rev = fc == "X1"
        elif "X1" in ends: k = next(k for k in ends if k.startswith("B-T")); pts = t_x1(k[2:], ends["X1"]); rev = fc == "X1"
        elif brd and "X2" in ends:                                                  # board inputs IN1 / IN2
            xc, zc = x2(ends["X2"]); p = int(ends[brd + "-J3"]); x = j3(brd, p)[0]
            via = {"A1": {12: (165.0, -98.5, 24.5), 11: (166.0, -98.5, 23.5)}, "A2": {12: (205.0, -98.5, 23.5), 11: (208.0, -98.5, 23.5)}}[brd][p]
            pts = x2s(ends["X2"]) + [via] + a_low(brd, p, -84.0, 21.5)[::-1]; rev = fc != "X2"
        elif brd and any(k.startswith("SP") for k in ends):                         # CAN stubs / fan feed from a board A pad
            s = next(k for k in ends if k.startswith("SP")); p = int(ends[brd + "-J3"]); x = j3(brd, p)[0]
            if s == "SP3": pts = a_pad(brd, p) + [(x, -76.0, 14.4), (243.0, -84.0, 16.0), (GX - 0.9, -91.5, 24.6), (GX - 0.9, GY, 24.6), (GX - 0.9, GY, 19.0)]; rev = fc == s
            else:
                west = brd == "A1"; xe = SPX - 1.5 if west else SPX + 1.5; ze = SPZ + 0.76 if west else SPZ - 0.76; ys = SP[s]
                mid = [(xe + (-5.0 if west else 5.0), ys, ze)] + ([(150.0, -88.5, 31.0)] if (west and s == "SP2") else [(200.0, -88.5, 30.0)] if s == "SP2" else [])
                pts = [(xe, ys, ze)] + mid + a_low(brd, p, -82.0, 24.0)[::-1]; rev = fc != s
        elif has("X2") and any(k.startswith("IN") for k in ends):                   # X2 -> input board J2 (Micro-Fit)
            k = next(k for k in ends if k.startswith("IN")); n = k[:3]; p = int(ends[k]); xt, zt = inj2(n, p)
            if n == "IN3":
                yl = -100.0 - 1.55 * ((p - 1) % 6); zl = 51.1 if p <= 6 else 52.7
                pts = x2s(ends["X2"]) + [(166.0, yl, zl), (xt, yl, zl), (xt, -93.3, zt), (xt, -88.5, zt)]
            else: pts = x2s(ends["X2"]) + [(xt, -94.5, zt), (xt, -88.5, zt)]
            rev = fc != "X2"
        elif has("X2", "B-J6"):
            t, yt, zt = bj6(int(ends["B-J6"])); xc, zc = x2(ends["X2"])
            pts = t + [(155.0, yt, 20.0), (159.5, -103.0, zc)] + x2s(ends["X2"])[::-1]; rev = fc == "X2"
        elif has("B-J6"):                                                           # CAN stub splice -> board B
            s = next(k for k in ends if k.startswith("SP")); t, yt, zt = bj6(int(ends["B-J6"]))
            pts = t + [(155.0, yt, 18.0), (159.5 if s == "SP1" else 158.0, -99.5, 33.0 if s == "SP1" else 31.5), (SPX - 6.5, SP[s], SPZ - 0.76), (SPX - 1.5, SP[s], SPZ - 0.76)]; rev = fc != "B-J6"
        elif has("X2"):                                                             # CAN X2 -> splice
            s = next(k for k in ends if k.startswith("SP"))
            pts = x2s(ends["X2"]) + [(180.5 if s == "SP1" else 178.5, SP[s], SPZ + 0.76), (SPX + 1.5, SP[s], SPZ + 0.76)]; rev = fc != "X2"
        elif has("IN2-J2", "SP4"):
            xt, zt = inj2("IN2", int(ends["IN2-J2"]))
            pts = [(xt, -88.5, zt), (xt, -96.0, 49.5), (236.0, -93.5, 44.0), (GX + 0.9, -91.5, 24.6), (GX + 0.9, GY, 24.6), (GX + 0.9, GY, 19.0)]; rev = fc != "IN2-J2"
        elif any(k.startswith("FAN") for k in ends):
            k = next(k for k in ends if k.startswith("FAN")); pts = fan(int(k[3]) - 1, ends[k] == "+"); rev = fc != k
        elif any(k.endswith("-J1") for k in ends):                                  # JST GH links
            k = next(k for k in ends if k[:2] in ("A1", "A2", "B-")); n = "B" if k.startswith("B") else k[:2]; p = int(ends[k])
            ghrank[n] = ghrank.get(n, -1) + 1; pts = gh(n, p, ghrank[n]); rev = fc != k
        assert pts, ("no route rule for", w, fc, tc)
        od, src = wire_od(r["Wire part number"])
        R[w] = dict(pts=pts[::-1] if rev else pts, od=od, od_source=src, color=r["Color"], rgb=RGB[r["Color"]], kind="wire", rows=[w],
                    desc=f"{w} {r['Signal']} | {r['AWG']} AWG {r['Color']} {r['Wire part number']} | {fc}.{fp} -> {tc}.{tp}")
    # USB cables (revD routes; U1 now starts at the bulkhead's rear socket: the revD plug block is gone)
    hy = (hb[2] + hb[3]) / 2; UZ = G["USB_Z"]; UX = G["USB_X"]
    usb = {"U1": [(UX, G["USB_REAR"] + 2.05, UZ), (UX, G["USB_REAR"] + 20.5, UZ), (UX - 12.0, -95.0, UZ - 3.0), (80.0, -95.0, UZ), (68.0, -95.0, 22.0), (27.0, -95.0, 22.0),
                  (27.0, -100.5, 22.0), (27.0, -100.5, 14.0), (32.0, -106.0, 9.5), (hb[1] + 2.1, hy, 7.0)]}
    # pigtails U2-U4: the USB-C plugs are not modelled; a cable ends 2 mm short of the board's receptacle. revD ran U3 and U4 through
    # each other and all three through the board edge; now U3 at y -99.7 / z 7.8, U4 beside and above it, U2 a short piece over the hub
    # (the hub stands 1.5 mm in front of board B's USB-C: no plug fits there - open problem, see the PR).
    XU = {n: Wb(n, -17.0974, 55.7412)[0] for n in ("B", "A1", "A2")}
    usb["U2"] = [(XU["B"], hb[3] - 9.0, 10.9), (XU["B"], hb[3] - 0.9, 10.9)]
    usb["U3"] = [(hb[1] + 2.1, -99.7, 7.8), (XU["A1"], -99.7, 7.8)]
    usb["U4"] = [(hb[1] + 2.1, -103.5, 7.8), (45.0, -103.5, 7.8), (50.0, -103.5, 9.1), (XU["A2"] - 6.0, -103.5, 9.1), (XU["A2"], -99.7, 7.8)]
    for k, pts in usb.items():
        cores = [r["Wire ID"] for r in rows if r["Twist/Shield group"] == k]
        R[k] = dict(pts=pts, od=OD_USB, od_source="ASSUMED (revD value, cable part TBD)", color="BK", rgb=CABLE_RGB, kind="cable", rows=cores,
                    desc=f"{k} USB 2.0 cable, round, OD {OD_USB:g} ASSUMED | cores {cores[0]}-{cores[-1]}")
    fails = []
    for w, d in R.items():
        segs, L, rmin = rounded(d["pts"], 3.0 * d["od"])
        d.update(segs=segs, length=round(L, 1), rmin=round(min(rmin, 999.0), 2), r_over_od=round(min(rmin, 999.0) / d["od"], 2))
        d["chain"] = rmin < 0.75 * d["od"]                           # a bend tighter than the cable itself cannot be swept: cylinders + spheres through the points (revD tube())
        if d["chain"]: d["length"] = round(sum(norm(sub(b, a)) for a, b in zip(d["pts"][:-1], d["pts"][1:])), 1)
        if d["kind"] == "wire" and rmin < 3.0 * d["od"] - 1e-6: fails.append((w, d["r_over_od"]))
    assert not fails, ("bend radius below 3 x OD", fails)
    covered = sorted(x for d in R.values() for x in d["rows"])
    assert covered == sorted(r["Wire ID"] for r in rows), "wire list rows without a route"
    return R

def G_from_meta(m, rear, usb_rear):
    return dict(Z_TOP=m["Z_TOP"], X0=m["X0"], CONN=m["CONN"], TZ=m["P"]["turret_z"], REAR=rear, IN_X={"IN3": 64.0, "IN1": 130.0, "IN2": 196.0},
                Z_IN=m["Z_TOP"] + m["P"]["so_m3_len"] + m["P"]["deck_t"] + m["P"]["in_boss"], GLAND=m["fan_lead_gland"]["at"], HUB=m["hub_bbox"],
                T58=m["T58"], TTOP=m["TTOP"], FAN=m["fan"], USB_X=m["USB_X"], USB_Z=m["P"]["usb_z"], USB_REAR=usb_rear)

# ---------------- solids (build123d; build_v2c.py and the checks) ----------------
def solid(d):
    from build123d import Edge, Wire, Face, Solid, Plane, Vector
    if d.get("chain"):
        s = Solid.make_sphere(d["od"] / 2).translate(Vector(*d["pts"][0]))
        for a, b in zip(d["pts"][:-1], d["pts"][1:]):
            a, b = Vector(*a), Vector(*b)
            s = s.fuse(Solid.make_cylinder(d["od"] / 2, (b - a).length, Plane(origin=a, z_dir=(b - a).normalized()))).fuse(Solid.make_sphere(d["od"] / 2).translate(b))
        return s.solids()[0] if len(s.solids()) == 1 else s
    es = [Edge.make_line(Vector(*s[1]), Vector(*s[2])) if s[0] == "L" else Edge.make_three_point_arc(Vector(*s[1]), Vector(*s[3]), Vector(*s[2])) for s in d["segs"]]
    p0 = Vector(*d["segs"][0][1]); d0 = (Vector(*d["segs"][0][2]) - p0).normalized()
    prof = Face(Wire([Edge.make_circle(d["od"] / 2, Plane(origin=p0, z_dir=d0))]))
    s = Solid.sweep(prof, Wire(es))
    assert s.is_valid and abs(s.volume - math.pi * d["od"] ** 2 / 4 * d["length"]) < 0.02 * s.volume + 0.5, ("sweep", d["desc"], s.volume)
    return s

# ---------------- lengths vs the wire list ----------------
def lengths(tab, write=False):
    """modelled length + service loop, up to 5 mm -> the CSV Length column where it says TBD; rows that differ > 10 % are listed"""
    path = csv_path(); raw = open(path, newline="", encoding="utf-8").read(); nl = "\r\n" if "\r\n" in raw else "\n"
    import re
    rows = list(csv.reader(raw.splitlines())); hdr = rows[0]; iL = hdr.index("Length (mm)"); iW = hdr.index("Wire ID"); iN = hdr.index("Notes")
    OLD = [r"route not in the model; est\. \d+ mm \([^)]*\)", r"not in the enclosure model; straight-line est\. \d+ mm board J6/J7 to input board J1 \(deck 32 mm above\)",
           r"fan leads enter through a plate pass-through that the enclosure model does not have yet \(TBD, enclosure job\)", r"pass-through TBD \(enclosure job\)"]
    by = {x: w for w, d in tab.items() for x in d["rows"]}; rep = []; filled = 0
    for r in rows[1:]:
        d = tab[by[r[iW]]]; rule = int(math.ceil((d["length"] + SERVICE_LOOP) / 5.0) * 5)
        if r[iL].strip() == "TBD":
            r[iL] = str(rule); filled += 1; st = "filled"; note = f"route: CPDM-HAR-200 model {d['length']:g} mm (harness_paths_v2c.py) + 2 x 15 loop"
            n0 = r[iN]
            for pat in OLD: r[iN] = re.sub(pat, note, r[iN])
            if r[iN] == n0: r[iN] = (n0 + "; " if n0 else "") + note
        else:
            st = "ok" if abs(float(r[iL]) - rule) <= 0.10 * float(r[iL]) else "DIFF"
        rep.append(dict(wire=r[iW], solid=by[r[iW]], model=d["length"], rule=rule, csv=r[iL], status=st))
    if write:
        import io
        buf = io.StringIO(); csv.writer(buf, lineterminator=nl).writerows(rows); open(path, "w", newline="", encoding="utf-8").write(buf.getvalue())
    return rep, filled

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "table":
        m = json.load(open(sys.argv[2])); tab = table(G_from_meta(m, m["harness_ends"]["REAR"], m["harness_ends"]["USB_REAR"]))
        json.dump(tab, open(sys.argv[3], "w"), indent=0); print(len(tab), "solids", sum(len(d["rows"]) for d in tab.values()), "rows")
    elif cmd == "lengths":
        tab = json.load(open(sys.argv[2])); rep, filled = lengths(tab, "--write" in sys.argv)
        for x in rep:
            if x["status"] != "ok": print(x)
        print("rows", len(rep), "filled", filled, "differ > 10 %:", sum(x["status"] == "DIFF" for x in rep))
