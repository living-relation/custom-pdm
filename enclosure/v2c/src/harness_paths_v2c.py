"""custom-pdm enclosure v2c revF: ONE path table for the inside-the-box harness (CPDM-HAR-200).
For every row of harness/enclosure-wire-list.csv (the master) a 3-D polyline from its From end to its To end, the wire OD and its
colour. build_v2c.py sweeps the STEP solids from it, fusion_v2c.py builds the same wires in Fusion from the JSON it writes
(<run>/<VAR>/harness_paths.json), and `lengths` writes the modelled lengths back into the CSV.
World frame = build_v2c.py (X east, Y north, Z up, mm).

Two steps (revF):
  1. initial(G): one rule per circuit gives each wire its ends and a first path (the topology: which lane, which side).
  2. harness_comb_v2c.py (the loom builder: fixed shapes in flat planes, no relaxation; hand data in harness_loom_data.py) gives
     each wire its path clear of the parts and of the other wires, every bend >= the wire's radius, and writes
     harness_routes_v2c.json (committed data). table(G) uses a stored route when its two ends still equal the rule's ends; a
     moved end makes the build fail until the loom builder is run again.

Ends (sources):
  X1 / X2: REAL cavity maps (revF), cavity_maps_v2c.json: IDs from TE customer drawing 0425-014-2400 rev H (all views = rear /
    grommet end; HD34-24-21S and HDP24-24-47S socket views; the 24-47 numbers follow the drawing's numbering line), positions
    from the rear cavity faces of the TE customer-view STEP models (21 / 47 faces at model z -39.4 / -39.2; the fit of the drawing
    to the 24-47 faces is 0.05 mm, so drawing up = model +y = world +Z, main key up). Seen from inside the box (the rear view) the
    viewer's right is world -X. A wire ends on the cavity face and leaves straight for 6 mm past the connector's rear end.
  board A J3 / J6, board B J6 / J7, input board J1 / J2: pad positions read from the .kicad_pcb files (A J3 pads +/-11.11 / 6.67 /
    2.22 at y -/+4.56; A J6 pads x -30.55, y -8.375 + 1.25 (p - 1); B J6 +/-1.5; B J7 pads (40.244, 51.475 - 1.25 (p - 1));
    input board J1 pads (58.15, 30.875 - 1.25 (p - 1)), J2 pads (10 / 13, 24 - 3 (p - 1))), placed with build_v2c.py W().
  Micro-Fit 43025-1200 and JST GHR-12V-S housings, the CAN / fan splices and the T5-T8 ring lugs are parts of the build (revF,
    build_v2c.py "wire ends"); a wire ends in its housing cavity (Micro-Fit: 9.0 behind the header face, rows 2.82 / 5.82 above
    the board; GH: at the pad row), in its splice or at the lug barrel mouth (Phoenix 3240083: 14 from the ring centre).
OD: enclosure_harness.py WP (GXL16 2.80, GXL12 3.65, M22759/16-20 1.52); ASSUMED where WP has none: 28 AWG 0.90 (JST GH
  SSHL-002T-P0.2 takes insulation OD 0.76-1.00; UL1571 28 AWG is about 0.9).
USB (revF): the hub sits under X2 with its upstream socket to the east (build_v2c.py). One solid per cable = round cable + its
  plug bodies. Plug bodies are labelled best guesses from the USB Type-C spec R2.0 (overmold cross-section max 12.35 x 6.5; the
  job brief's typical plug + strain relief 25-35 mm): straight plug = overmold 19 + boot 8 (27 behind the socket face);
  right-angle plug = block 12.35 x 6.5 x 11 deep + boot 6 (the board sockets face the front wall 27 mm away, so a straight plug
  cannot fit there). U1 = USB 2.0 C-to-C cable, OD 4.0 ASSUMED (cable part TBD), right-angle plug down at the bulkhead, straight
  plug into the hub. U2-U4 = 4-core pigtails, OD 3.0 ASSUMED, right-angle plug at the board, open end at the hub pads (the cable
  ends at the hub edge; pad order TBD). Cable bend radius >= 4 x OD (the spec's cable flex test bends at 3.7 x OD, 3.8.1.4).
Bend radius: wires 3 x OD, cables 4 x OD, on the centre line; table(strict=True) fails a tighter bend.
Usage: python harness_paths_v2c.py table <meta.json> <out.json> | lengths <harness_paths.json> [--write]
"""
import os, sys, csv, json, math

RGB = {"RD": (0.80, 0.10, 0.10), "WH": (0.92, 0.92, 0.88), "VT": (0.50, 0.20, 0.70), "BK": (0.08, 0.08, 0.08), "YE": (0.95, 0.80, 0.10),
       "GN": (0.10, 0.60, 0.20), "GY": (0.50, 0.50, 0.50)}
OD_28AWG = 0.90; OD_USB = 4.0; OD_PIG = 3.0; CABLE_RGB = (0.12, 0.12, 0.14); R_WIRE = 3.0; R_CABLE = 4.0
SERVICE_LOOP = 2 * 15.0                         # circuit-list.md length rule: model route + 2 x 15 mm service loop, up to 5 mm
HERE = os.path.dirname(os.path.abspath(__file__))
CAV = json.load(open(os.path.join(HERE, "cavity_maps_v2c.json")))
ROUTEF = os.path.join(HERE, "harness_routes_v2c.json")
CAV_Z = {"X1": 39.4, "X2": 39.2}                # cavity face behind the mating face (TE model z), mm
USB_SOCK = dict(dx=23.69, y=-97.64, z=7.61)     # board USB-C (GCT USB4085) opening: centre x from the board's west edge, face y, centre z (measured on the board STEPs)
HUB_LOCAL = dict(pcb=(20.32, 30.48, 1.57), sock_y=31.59, sock_x=10.16, sock_z=2.67, holes=((2.54, 2.54), (17.78, 2.54), (2.54, 27.94), (17.78, 27.94)))   # Adafruit 5997 STEP, own frame
PLUG = dict(w=12.35, t=6.5, straight=19.0, boot=8.0, boot_d=5.5, ra_depth=11.0, ra_boot=6.0, ra_axis=4.0, gap=0.5)
def wt_root(): return os.environ.get("WT") or os.path.abspath(os.path.join(HERE, "..", "..", ".."))
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

# ---------------- the rules: ends + first path of every wire ----------------
PX = {1: -11.11, 2: -6.67, 3: -2.22, 4: 2.22, 5: 6.67, 6: 11.11, 7: 11.11, 8: 6.67, 9: 2.22, 10: -2.22, 11: -6.67, 12: -11.11}   # board A J3 pads (KiCad x)
A2_LANE = {8: (-104.9, 12.6), 9: (-102.0, 12.6), 10: (-99.1, 12.6), 6: (-104.9, 15.4), 5: (-102.0, 15.4), 4: (-99.1, 15.4), 3: (-96.2, 15.4)}
SPLICE = dict(x=185.0, y={"SP1": -111.0, "SP2": -116.0}, z=58.5, L=25.0, d=4.5, fan_dx=1.6, fan_z=(16.0, 30.0), fan_d=3.2)   # CAN splices lie along x; fan splices stand above the cord grip
STUB = 10.0                                    # straight wire behind a box connector's rear end before the first bend (mm)
T58_ANG = {"T5": 240.0, "T6": 240.0, "T7": 235.0, "T8": 240.0}   # ring-lug barrel directions (deg from +X): south-west, where the lanes to X1 come from
def t58_mouth(G, k):
    """barrel mouth of a T5-T8 ring lug (Phoenix 3240083: 14 from the ring centre) and the barrel direction"""
    X, Y = G["T58"][k]; a = math.radians(T58_ANG[k]); return (X + 14 * math.cos(a), Y + 14 * math.sin(a), G["TTOP"] + 2.8), (math.cos(a), math.sin(a), 0.0)
SLEEVE = dict(pn="RNF-100-3-16-0-SP", id=3.0, od=4.02)
def cav(G, k, c):
    """world (x, z) of a cavity: the map holds TE model x / y; model x -> world X, model y -> world Z"""
    e = CAV[k][str(c)]; return G["CONN"][k] + e["x"], G["TZ"] + e["y"]
def hub_frame(G):
    HX, HY, HZ = G["HUBF"]; h = HUB_LOCAL
    return dict(HX=HX, HY=HY, HZ=HZ, top=HZ + h["pcb"][2], x1=HX + h["pcb"][1], y0=HY - h["pcb"][0], sock=(HX + h["sock_y"], HY - h["sock_x"], HZ + h["sock_z"]),
                holes=[(HX + hy, HY - hx) for hx, hy in h["holes"]])
def sleeve_paths(G):
    """two cut lengths of the fan-lead sleeve under the plate: over fan 2's leads between the fans, and over all four leads from
    fan 1's lead exit to the cord grip (it ends 1.5 below the plate; the cord grip seals on the adhesive heat shrink above)"""
    xc = sum(G["FAN"]["x"]) / 2; GX, GY = G["GLAND"]; y0, y1 = G["FAN"]["y"]
    return [[(xc, y1 - 15.5, -42.6), (xc, y0 - 8.0, -42.6)], [(xc, y0 - 15.5, -42.05), (xc, -95.0, -42.05), (GX, GY, -33.0), (GX, GY, -9.5)]]
def initial(G):
    ZT = G["Z_TOP"]; X0 = G["X0"]; CONN = G["CONN"]; TZ = G["TZ"]; Y1 = G["REAR"]["X1"]; Y2 = G["REAR"]["X2"]; C1 = G["CAVY"]["X1"]; C2 = G["CAVY"]["X2"]; IN_X = G["IN_X"]
    ZI = G["Z_IN"] + 1.51; GX, GY = G["GLAND"]; T58 = G["T58"]; HF = hub_frame(G)
    def Wb(n, xk, yk): return (X0[n] + xk + 37.846, -(yk + 33.274))
    def j3(n, p):
        x, y = Wb(n, PX[p], -4.56 if p <= 6 else 4.56); return x, y, (17.2 if p <= 6 else 14.4)   # lane height: north row over south row
    def x1e(c): xc, zc = cav(G, "X1", c); return [(xc, Y1 + STUB, zc), (xc, C1, zc)]            # ... -> stub -> cavity face
    def x2s(k): xc, zc = cav(G, "X2", k); return [(xc, C2, zc), (xc, Y2 + STUB, zc)]            # cavity face -> stub -> ...
    def inj2(n, p): return IN_X[n] + 24.0 - 3.0 * ((p - 1) % 6), ZI + (2.82 if p <= 6 else 5.82)
    SPX = SPLICE["x"]; SP = SPLICE["y"]; SPZ = SPLICE["z"]; SL = SPLICE["L"] / 2 + 2.5
    def sp_end(s, west, hi): xe = SPX + (-1.5 if west else 1.5); ze = SPZ + (0.80 if hi else -0.80); return [(xe, SP[s], ze), (SPX + (-SL if west else SL), SP[s], ze)]
    R = {}
    def a_pad(n, p): x, y, z = j3(n, p); return [(x, y, ZT), (x, y, z)]
    def a_x1(n, p, c):                                                              # board A J3 pad -> X1 (16 AWG)
        x, y, z = j3(n, p); xc, zc = cav(G, "X1", c); pts = a_pad(n, p)
        if n == "A1": pts += [(x, -78.0, z), (xc + 11.0, -92.0, z + 0.5 * (zc - z))]
        else:
            yl, zl = A2_LANE[p]; pts += [(x, yl, z), (212.0, yl, z), (204.0, yl, zl), (150.0, yl, zl), (xc + 14.0, -100.0, zc)]
        return pts + x1e(c)
    def t_x1(k, c):                                                                 # board B T5-T8 lug barrel mouth -> X1 (12 AWG)
        A, u = t58_mouth(G, k); xc, zc = cav(G, "X1", c)                            # first path only: the loom data holds the real one
        return [A, add(A, u, 5.0), (xc - 6.0, -96.0, zc)] + x1e(c)
    def a_low(n, p, y1, z1):                                                        # lane end of a 20 AWG wire on a board A pad, pad first
        x, y, z = j3(n, p); return a_pad(n, p) + [(x, y1 + 6.0, z), (x, y1, z1)]
    def bj6(p):                                                                     # board B J6 pad -> east along the front strip, above the USB pigtail U2 and the tie mounts
        px = X0["B"] + 37.846 + (-1.5 if p in (1, 3) else 1.5); py = -(33.274 + (-1.5 if p <= 2 else 1.5)); zl = 12.12 if p <= 2 else 10.6
        yt = -104.0 - 1.8 * (p - 1); zt = 12.0
        return [(px, py, ZT), (px, py, zl), (px, -90.0, zl), (px + 10.0, yt, zt), (120.0, yt, zt)]
    def gh(n, p, rank):                                                             # board GH connector -> input board J1 (28 AWG)
        z1 = ZI + 1.0
        if n == "B":
            y = -84.749 + 1.25 * (p - 1); xc = 70.7 - 0.92 * (p - 1); xi = IN_X["IN3"] + 30.875 - 1.25 * (p - 1)
            return [(76.144, y, ZT + 6.3), (76.144, y, 15.5), (xc, y - 0.5 * (76.144 - xc), 15.5), (xc + 1.0, -92.3, 15.5), (xc + 1.0, -92.3, 48.1), (xc + 1.0, -86.0, 48.1), (xi, -62.0, 48.1),
                    (xi, -13.3, 48.1), (xi, -13.3, z1), (xi, -16.5, z1)]
        y = -24.899 - 1.25 * (p - 1); xr = X0[n] - 1.0
        xk = {"A1": 127.5, "A2": 232.5}[n] + 0.95 * rank; yn = -1.9 - 0.95 * rank if n == "A1" else -9.5 + 0.95 * rank
        xi = IN_X["IN1" if n == "A1" else "IN2"] + 30.875 - 1.25 * (p - 1)
        return [(X0[n] + 1.9, y, ZT + 1.0), (xr, y, ZT + 1.0), (xr, y, 26.5), (xk, y, 26.5), (xk, yn, 26.5), (xk, yn, z1), (xi, yn, z1), (xi, -16.5, z1)]
    def fan(f, plus):                                                               # fan lead: fan retainer corner -> through the cord grip -> its solder splice
        fy = G["FAN"]["y"][f]; xl = sum(G["FAN"]["x"]) / 2 + (-0.5 if plus else 0.5); zb = G["FAN"]["z"] - 15.0; zr = -41.5 if f == 0 else -42.6
        gx = GX + (-0.48 if plus else 0.48); gy = GY + (-0.48 if f == 0 else 0.48); sx = GX + (-SPLICE["fan_dx"] if plus else SPLICE["fan_dx"])
        return [(xl, fy - 12.0, zb), (xl, fy - 12.0, zr), (xl, -95.0, zr), (gx, gy, -33.0), (gx, gy, 12.5), (sx, gy, 15.5), (sx, gy, 20.0)]
    def sp_fan(plus): sx = GX + (-SPLICE["fan_dx"] if plus else SPLICE["fan_dx"]); return [(sx, GY, 34.0), (sx, GY, 22.0)]   # the 20 AWG wire comes down into the fan splice
    rows = read_rows(); ghrank = {}
    for r in rows:
        w = r["Wire ID"]; fc, fp, tc, tp = r["From connector"], r["From pin"], r["To connector"], r["To pin"]; pts = None; rev = False; fixed = False
        ends = {fc: fp, tc: tp}
        def has(*c): return all(k in ends for k in c)
        if r["Signal group"].startswith("C11"): continue                           # USB cores: one cable solid per cable, below
        brd = next((k[:2] for k in ends if k in ("A1-J3", "A2-J3")), None)
        if brd and "X1" in ends: pts = a_x1(brd, int(ends[brd + "-J3"]), ends["X1"]); rev = fc == "X1"
        elif "X1" in ends: k = next(k for k in ends if k.startswith("B-T")); pts = t_x1(k[2:], ends["X1"]); rev = fc == "X1"
        elif brd and "X2" in ends:                                                  # board inputs IN1 / IN2
            p = int(ends[brd + "-J3"])
            pts = x2s(ends["X2"]) + [(G["CONN"]["X2"] + (-14.0 if brd == "A1" else 16.0), -96.0, 24.0)] + a_low(brd, p, -84.0, 21.5)[::-1]; rev = fc != "X2"
        elif brd and any(k.startswith("SP") for k in ends):                         # CAN stubs / fan feed from a board A pad
            s = next(k for k in ends if k.startswith("SP")); p = int(ends[brd + "-J3"]); x = j3(brd, p)[0]
            if s == "SP3": pts = a_pad(brd, p) + [(x, -76.0, 14.4), (243.0, -86.0, 30.0), (GX - 1.6, -93.0, 36.0)] + sp_fan(True); rev = fc == s
            else: pts = sp_end(s, brd == "A1", True) + a_low(brd, p, -80.0, 28.0)[::-1]; rev = fc != s
        elif has("X2") and any(k.startswith("IN") for k in ends):                   # X2 -> input board J2 (Micro-Fit)
            k = next(k for k in ends if k.startswith("IN")); n = k[:3]; p = int(ends[k]); xt, zt = inj2(n, p)
            if n == "IN3":
                yl = -100.0 - 1.55 * ((p - 1) % 6); zl = 51.1 if p <= 6 else 52.7
                pts = x2s(ends["X2"]) + [(166.0, yl, zl), (xt, yl, zl), (xt, -95.0, zt), (xt, -88.5, zt)]
            else: pts = x2s(ends["X2"]) + [(xt, -95.0, zt), (xt, -88.5, zt)]
            rev = fc != "X2"
        elif has("X2", "B-J6"):
            pts = bj6(int(ends["B-J6"])) + [(150.0, -104.0, 13.0)] + x2s(ends["X2"])[::-1]; rev = fc == "X2"
        elif has("B-J6"):                                                           # CAN stub splice -> board B
            s = next(k for k in ends if k.startswith("SP")); pts = bj6(int(ends["B-J6"])) + [(145.0, -98.0, 30.0)] + sp_end(s, True, False)[::-1]; rev = fc != "B-J6"
        elif has("X2"):                                                             # CAN X2 -> splice
            s = next(k for k in ends if k.startswith("SP")); pts = x2s(ends["X2"]) + sp_end(s, False, False)[::-1]; rev = fc != "X2"
        elif has("IN2-J2", "SP4"):
            xt, zt = inj2("IN2", int(ends["IN2-J2"]))
            pts = [(xt, -88.5, zt), (xt, -95.0, zt), (GX + 1.6, -96.0, 40.0)] + sp_fan(False); rev = fc != "IN2-J2"
        elif any(k.startswith("FAN") for k in ends):
            k = next(k for k in ends if k.startswith("FAN")); pts = fan(int(k[3]) - 1, ends[k] == "+"); rev = fc != k; fixed = True
        elif any(k.endswith("-J1") for k in ends):                                  # JST GH links
            k = next(k for k in ends if k[:2] in ("A1", "A2", "B-")); n = "B" if k.startswith("B") else k[:2]; p = int(ends[k])
            ghrank[n] = ghrank.get(n, -1) + 1; pts = gh(n, p, ghrank[n]); rev = fc != k
        assert pts, ("no route rule for", w, fc, tc)
        od, src = wire_od(r["Wire part number"])
        R[w] = dict(pts=pts[::-1] if rev else pts, od=od, od_source=src, color=r["Color"], rgb=RGB[r["Color"]], kind="wire", rows=[w], rmul=R_WIRE, fixed=fixed, plugs=[],
                    desc=f"{w} {r['Signal']} | {r['AWG']} AWG {r['Color']} {r['Wire part number']} | {fc}.{fp} -> {tc}.{tp}")
    # ---- USB cables: cable + plug bodies (boxes x0 x1 y0 y1 z0 z1, cylinders p0 p1 d) ----
    P_ = PLUG; hw = P_["w"] / 2; ht = P_["t"] / 2; UX = G["USB_X"]; UZ = G["USB_Z"]; UR = G["USB_REAR"]; sx, sy, sz = HF["sock"]
    ya = UR + P_["ra_depth"] / 2; x0 = sx + P_["gap"]; x1_ = x0 + P_["straight"]; x2_ = x1_ + P_["boot"]
    usb = {"U1": dict(pts=[(UX, ya, UZ - ht), (UX, ya, UZ - ht - P_["boot"]), (UX, ya, 2.6), (x2_ + 15.0, sy, 2.6), (x2_ + 4.0, sy, sz), (x2_, sy, sz), (x1_, sy, sz)], od=OD_USB,
                      plugs=[("box", UX - hw, UX + hw, UR, UR + P_["ra_depth"], UZ - ht, UZ + ht), ("cyl", (UX, ya, UZ - ht), (UX, ya, UZ - ht - P_["boot"]), P_["boot_d"]),
                             ("box", x0, x1_, sy - hw, sy + hw, sz - ht, sz + ht), ("cyl", (x1_, sy, sz), (x2_, sy, sz), P_["boot_d"])],
                      what="USB 2.0 C-to-C cable: right-angle plug (down) in the bulkhead's rear socket, straight plug in the hub's upstream socket")}
    yb = USB_SOCK["y"] - P_["ra_axis"]; zb = USB_SOCK["z"]
    for k, n, east, xe, ye in (("U2", "B", True, HF["HX"] + 4.5, -113.5), ("U3", "A1", True, HF["HX"] + 6.0, yb), ("U4", "A2", False, HF["x1"] - 6.5, yb)):
        xs = X0[n] + USB_SOCK["dx"]; sg = 1.0 if east else -1.0; xb = xs + sg * hw; xq = xb + sg * P_["ra_boot"]
        mid = [(100.0, yb, zb), (127.0, ye, zb)] if k == "U2" else []
        usb[k] = dict(pts=[(xb, yb, zb), (xq, yb, zb)] + mid + [(xe, ye, zb)], od=OD_PIG, nfix=(2, 1),
                      plugs=[("box", xs - hw, xs + hw, USB_SOCK["y"] - P_["ra_depth"], USB_SOCK["y"], zb - ht, zb + ht), ("cyl", (xb, yb, zb), (xq, yb, zb), 4.5)],
                      what=f"USB 2.0 pigtail: right-angle plug in board {n}'s USB-C socket, open end at the hub's downstream pads")
    for k, u in usb.items():
        cores = [r["Wire ID"] for r in rows if r["Twist/Shield group"] == k]
        R[k] = dict(pts=u["pts"], od=u["od"], od_source="ASSUMED (cable part TBD)", color="BK", rgb=CABLE_RGB, kind="cable", rows=cores, rmul=R_CABLE, fixed=False, plugs=u["plugs"],
                    nfix=u.get("nfix", (2, 2)), desc=f"{k} {u['what']} | round, OD {u['od']:g} ASSUMED, plug bodies best guess (USB Type-C spec envelope) | cores {cores[0]}-{cores[-1]}")
    for d in R.values(): d.setdefault("nfix", (2, 2)); d["pts"] = [tuple(round(float(c), 4) for c in p) for p in d["pts"]]
    assert sorted(x for d in R.values() for x in d["rows"]) == sorted(r["Wire ID"] for r in rows), "wire list rows without a route"
    return R

def routes():
    return json.load(open(ROUTEF)).get("routes", {}) if os.path.exists(ROUTEF) else {}
def same_ends(a, b, tol=0.02): return norm(sub(a[0], b[0])) < tol and norm(sub(a[-1], b[-1])) < tol
def finish(d):
    """segs / length / smallest bend of one entry (pts set)"""
    segs, L, rmin = rounded(d["pts"], d["rmul"] * d["od"])
    d.update(segs=segs, length=round(L, 1), rmin=round(min(rmin, 999.0), 2), r_over_od=round(min(rmin, 999.0) / d["od"], 2)); return d
def table(G, strict=True, use_routes=True):
    """the path table: the rules' ends, the routed paths (harness_routes_v2c.json) where present. strict: fail on a wire whose
    stored route no longer fits its ends (run harness_comb_v2c.py again) and on a bend below the wire's radius."""
    R = initial(G); RT = routes() if use_routes else {}; stale = []; tight = []
    for w, d in R.items():
        d["rule_pts"] = d["pts"]; rt = RT.get(w)
        if rt and same_ends(rt, d["pts"]): d["pts"] = [tuple(p) for p in rt]; d["routed"] = True
        else:
            d["routed"] = False
            if use_routes and not d["fixed"]: stale.append(w)
        finish(d)
        if d["rmin"] < d["rmul"] * d["od"] - 1e-6: tight.append((w, d["r_over_od"]))
    if strict:
        assert not stale, ("no stored route for these wires' ends: run harness_comb_v2c.py (enclosure/v2c/src) and commit harness_routes_v2c.json", stale[:12], len(stale))
        assert not tight, ("bend radius below the wire's minimum", tight)
    return R

def G_from_meta(m):
    e = m["harness_ends"]
    return dict(Z_TOP=m["Z_TOP"], X0=m["X0"], CONN=m["CONN"], TZ=m["P"]["turret_z"], REAR=e["REAR"], CAVY=e["CAVY"], IN_X={"IN3": 64.0, "IN1": 130.0, "IN2": 196.0},
                Z_IN=m["Z_TOP"] + m["P"]["so_m3_len"] + m["P"]["deck_t"] + m["P"]["in_boss"], GLAND=m["fan_lead_gland"]["at"], HUBF=e["HUBF"],
                T58=m["T58"], TTOP=m["TTOP"], FAN=m["fan"], USB_X=m["USB_X"], USB_Z=m["P"]["usb_z"], USB_REAR=e["USB_REAR"])

# ---------------- solids (build123d; build_v2c.py and the checks) ----------------
def sweep(pts_or_segs, od, id_=0.0):
    from build123d import Edge, Wire, Face, Solid, Plane, Vector
    segs = pts_or_segs
    es = [Edge.make_line(Vector(*s[1]), Vector(*s[2])) if s[0] == "L" else Edge.make_three_point_arc(Vector(*s[1]), Vector(*s[3]), Vector(*s[2])) for s in segs]
    p0 = Vector(*segs[0][1]); d0 = (Vector(*segs[0][2]) - p0).normalized(); pl = Plane(origin=p0, z_dir=d0)
    prof = Face(Wire([Edge.make_circle(od / 2, pl)]), [Wire([Edge.make_circle(id_ / 2, pl)])] if id_ else [])
    return Solid.sweep(prof, Wire(es))
def plug_solids(d):
    from build123d import Solid, Plane, Vector, Box, Pos
    out = []
    for p in d.get("plugs", []):
        if p[0] == "box": _, x0, x1, y0, y1, z0, z1 = p; out.append(Solid.make_box(x1 - x0, y1 - y0, z1 - z0, Plane(origin=(x0, y0, z0))))
        else: a, b = Vector(*p[1]), Vector(*p[2]); out.append(Solid.make_cylinder(p[3] / 2, (b - a).length, Plane(origin=a, z_dir=(b - a).normalized())))
    return out
def solid(d):
    s = sweep(d["segs"], d["od"])
    assert s.is_valid and abs(s.volume - math.pi * d["od"] ** 2 / 4 * d["length"]) < 0.02 * s.volume + 0.5, ("sweep", d["desc"], s.volume)
    for p in plug_solids(d): s = s.fuse(p)
    if d.get("plugs"):
        ss = s.solids(); assert len(ss) == 1, ("cable + plugs must be one solid", d["desc"][:30], len(ss)); s = ss[0]
    return s
def sleeve_solids(G):
    out = []; tot = 0.0
    for pts in sleeve_paths(G):
        segs, L, rmin = rounded(pts, 2.7); out.append(sweep(segs, SLEEVE["od"], SLEEVE["id"])); tot += L
    return out, round(tot, 1)

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
        m = json.load(open(sys.argv[2])); tab = table(G_from_meta(m))
        json.dump(tab, open(sys.argv[3], "w"), indent=0); print(len(tab), "solids", sum(len(d["rows"]) for d in tab.values()), "rows")
    elif cmd == "lengths":
        tab = json.load(open(sys.argv[2])); rep, filled = lengths(tab, "--write" in sys.argv)
        for x in rep:
            if x["status"] != "ok": print(x)
        print("rows", len(rep), "filled", filled, "differ > 10 %:", sum(x["status"] == "DIFF" for x in rep))
