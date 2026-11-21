"""custom-pdm enclosure v2c revF: the loom builder (replaces the relaxing router harness_route_v2c.py, which did not converge).
Deterministic, no relaxation: every wire of the path table gets ONE polyline that is built from its two ends and a short list of
allowed shapes, and a shape is only taken when it is proven free at that moment:
  - a wire leaves a box connector (X1 / X2) straight for STUB mm past the connector's rear end (TE: keep the wire straight behind
    the rear seal before the first bend), a pad straight up to its lane height, a Micro-Fit housing straight for MF_STRAIGHT;
  - it then turns (90 deg, radius 3 x OD) into a flat plane y = const across the front bay, runs in that plane on its own height
    (horizontal runs, vertical drops or 45 deg ramps) and turns out of the plane into its other end. Planes and heights are tried
    in a fixed order (nearest plane, simplest shape first), so wires of one connector stack into flat combed layers;
  - two ends that face each other (X2 stubs and the Micro-Fit housings) get a C-loop through a second plane;
  - "free" = every 0.5 mm point of the filleted centre line keeps r1 + r2 + GAP from every wire already placed and from the still
    unplaced wires' straight end pieces, and r + PART from every part (a 0.5 mm distance field of the draft build's surfaces).
Wires with a hand rule (fan leads, GH links, USB cables, T5-T8) keep the rule path of harness_paths_v2c.initial / HAND below.
Order = ORDER below (a wire whose cavity lies ahead of another in the turn direction goes first). A wire that finds no shape is
reported; fix it by order / plane / lane data here, not by iteration. wirecheck_v2c.py (exact solids) stays the judge.
Usage: $CAD_PY harness_comb_v2c.py F1   (RUN_DIR of a DRAFT build: HARNESS_DRAFT=1 build_v2c.py)  -> <src>/harness_routes_v2c.json"""
import os, sys, json, glob, math
import numpy as np
from scipy.spatial import cKDTree
import harness_paths_v2c as HP
GAP = 0.08; PART = 0.55; STEP = 0.5; STUB = 10.0; MF_STRAIGHT = 4.0; MF_REAR = -89.6; EXEMPT = 9.0
SKIP = ("harness-",); NOFIELD = ("splices-CAN", "vendor-plug")

# ---------------- parts: surface points and distance field ----------------
def tri_points(V, T, spacing):
    a, b, c = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    e = np.maximum(np.maximum(np.linalg.norm(b - a, axis=1), np.linalg.norm(c - a, axis=1)), np.linalg.norm(c - b, axis=1))
    k = np.maximum(1, np.ceil(e / spacing).astype(int)); out = [V]
    for kk in np.unique(k):
        m = k == kk; ii, jj = np.meshgrid(np.arange(kk), np.arange(kk), indexing="ij"); lo = (ii + jj) < kk; up = (ii + jj) < kk - 1
        uv = np.concatenate([np.stack([(ii[lo] + 1 / 3) / kk, (jj[lo] + 1 / 3) / kk], 1), np.stack([(ii[up] + 2 / 3) / kk, (jj[up] + 2 / 3) / kk], 1)])
        A, B, C = a[m][:, None, :], b[m][:, None, :], c[m][:, None, :]
        out.append((A + uv[None, :, 0:1] * (B - A) + uv[None, :, 1:2] * (C - A)).reshape(-1, 3))
    return np.concatenate(out)
def surface_points(out_dir, spacing=0.6, zmin=-2.0, skip=SKIP):
    """points on every placed part's surface above zmin (the box inside), cached beside the BREPs; also the item of each point"""
    breps = [f for f in sorted(glob.glob(os.path.join(out_dir, "brep", "*.brep"))) if not os.path.basename(f).startswith(skip)]
    cache = os.path.join(out_dir, f"surface_pts_{spacing:g}_{zmin:g}.npz")
    if os.path.exists(cache) and os.path.getmtime(cache) > max(os.path.getmtime(f) for f in breps):
        z = np.load(cache, allow_pickle=True); return z["pts"], z["item"], list(z["names"])
    from build123d import import_brep
    P = []; I = []; names = []
    for n, f in enumerate(breps):
        names.append(os.path.basename(f)[:-5])
        for face in import_brep(f).faces():                          # face by face: one face without a mesh must not lose the part
            if face.bounding_box().max.Z < zmin: continue
            try: v, t = face.tessellate(0.05, 0.3)
            except Exception: v, t = [], []
            if not len(t): continue
            p = tri_points(np.array([(q.X, q.Y, q.Z) for q in v]), np.array(t), spacing); p = p[p[:, 2] > zmin]
            P.append(p.astype(np.float32)); I.append(np.full(len(p), n, np.int16))
    P = np.concatenate(P); I = np.concatenate(I); np.savez(cache, pts=P, item=I, names=np.array(names)); return P, I, names
class Field:
    """distance (mm) from a point to the nearest part surface, 0.5 mm voxels (the CAN splices are left out: the loom places them)"""
    def __init__(s, out_dir, h=0.5):
        cache = os.path.join(out_dir, f"part_field_{h:g}.npz")
        if os.path.exists(cache): z = np.load(cache); s.lo = z["lo"]; s.h = float(z["h"]); s.D = z["D"]; return
        from scipy import ndimage
        P, I, names = surface_points(out_dir); keep = ~np.isin(I, [i for i, n in enumerate(names) if str(n).startswith(NOFIELD)]); P = P[keep]
        s.h = h; s.lo = np.floor(P.min(0)) - 2.0; n = np.ceil((P.max(0) + 2.0 - s.lo) / h).astype(int) + 1; occ = np.zeros(n, bool)
        j = np.round((P - s.lo) / h).astype(int); occ[j[:, 0], j[:, 1], j[:, 2]] = True
        s.D = (ndimage.distance_transform_edt(~occ) * h).astype(np.float16); np.savez(cache, lo=s.lo, h=h, D=s.D)
    def dist(s, P):
        j = np.clip(np.round((np.asarray(P) - s.lo) / s.h).astype(int), 0, np.array(s.D.shape) - 1); return s.D[j[:, 0], j[:, 1], j[:, 2]].astype(float)

# ---------------- centre-line samples ----------------
def samples(pts, R):
    """0.5 mm points along the filleted polyline, their arc length, the smallest fillet radius, the length"""
    segs, L, rmin = HP.rounded(pts, R); out = []
    for s in segs:
        if s[0] == "L":
            a, b = np.array(s[1]), np.array(s[2]); n = max(1, int(np.linalg.norm(b - a) / STEP)); out.append(a + (b - a) * (np.arange(n + 1) / n)[:, None])
        else:
            p1, p2, c = np.array(s[1]), np.array(s[2]), np.array(s[4]); v1, v2 = p1 - c, p2 - c
            th = math.acos(max(-1.0, min(1.0, float(v1 @ v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))))); n = max(2, int(s[5] * th / STEP)); q = np.arange(n + 1) / n
            out.append(c + (np.sin((1 - q) * th)[:, None] * v1 + np.sin(q * th)[:, None] * v2) / max(math.sin(th), 1e-9))
    P = np.concatenate(out); S = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]); return P, S, rmin, L

class Loom:
    def __init__(s, field): s.F = field; s.obs = {}; s.path = {}; s.why = {}
    def set_obs(s, owner, P, r): s.obs[owner] = (np.asarray(P, float), float(r)); s._t = None
    def tree(s, w):
        if getattr(s, "_t", None) is None or s._t[0] != w:
            ks = [k for k in s.obs if k != w]; P = np.concatenate([s.obs[k][0] for k in ks]); Rr = np.concatenate([np.full(len(s.obs[k][0]), s.obs[k][1]) for k in ks])
            own = np.concatenate([np.full(len(s.obs[k][0]), i) for i, k in enumerate(ks)]); s._t = (w, cKDTree(P), Rr, own, ks)
        return s._t[1:]
    def check(s, w, pts, od, rmul, part=PART, exempt=EXEMPT, who=False):
        R = rmul * od; r = od / 2; P, S, rmin, L = samples(pts, R)
        if rmin < R - 1e-6: return "bend"
        mid = (S > exempt) & (S < L - exempt)
        if s.F is not None and mid.any():
            dd = s.F.dist(P[mid])
            if (dd < r + part).any(): return "part" + (" at %.0f %.0f %.0f gap %.2f" % (*P[mid][int(dd.argmin())], dd.min() - r) if who else "")
        t, Rr, own, ks = s.tree(w); d, i = t.query(P, k=8, distance_upper_bound=r + 2.3 + GAP); ok = np.isfinite(d); i = np.minimum(i, len(Rr) - 1)
        bad = ok & (d < r + Rr[i] + GAP)
        if bad.any(): return "wire " + ",".join(sorted({ks[j] for j in own[i[bad]]})[:4]) if who else "wire"
        return None
    def place(s, w, pts, od): P, S, rmin, L = samples(pts, 3.0 * od if w[0] == "W" else 4.0 * od); s.set_obs(w, P, od / 2); s.path[w] = [tuple(round(float(c), 4) for c in p) for p in pts]

# ---------------- ends ----------------
def end_info(G, row, pts, at_from):
    """one wire end: kind, the fixed lead (terminal outwards) and where / how it meets the bay planes"""
    c = row["From connector"] if at_from else row["To connector"]; P = pts[0] if at_from else pts[-1]; Q = pts[1] if at_from else pts[-2]
    if c in ("X1", "X2"): return dict(kind="conn", lead=[P], x=P[0], z=P[2], dir=1, y0=G["REAR"][c] + STUB)
    if c.endswith("-J3"): return dict(kind="pad", lead=[P], x=P[0], z=None, dir=-1, y0=P[1], pad=c + "." + (row["From pin"] if at_from else row["To pin"]))
    if c == "B-J6":                                               # the four pads sit between the OUT risers: both pad columns leave south through the 3.9 mm gap at x 35.1..39.0
        p = int(row["From pin"] if at_from else row["To pin"]); return dict(kind="pad", lead=[P], pre=(P[0], P[1]), x=36.1 if p in (1, 3) else 37.75, z=None, dir=-1, y0=-40.0, pad=c + "." + str(p))
    if c.endswith("-J2"): return dict(kind="mf", lead=[P], x=P[0], z=P[2], dir=-1, y0=MF_REAR - MF_STRAIGHT)
    if c.startswith("SP") and abs(Q[1] - P[1]) < 1e-6 and abs(Q[2] - P[2]) < 1e-6: return dict(kind="splice", lead=[P, Q], x=Q[0], z=Q[2], dir=0, y0=P[1])
    return dict(kind="fixed")
def lane_z(e, od):
    """lane height above the board for a pad wire: the pad row nearer the bay (south) runs low, the other row above it"""
    c, p = e["pad"].split("."); p = int(p)
    if c == "B-J6": return 12.2 if p <= 2 else 10.5
    return 14.4 if p > 6 else 17.35

def mids(xa, za, xb, zb, R, zgrid, simple, keep="a"):
    """in-plane way points (x, z) between two plane points, simplest first. keep = the end whose height the long run keeps"""
    dx = xb - xa; dz = zb - za; sg = 1.0 if dx >= 0 else -1.0; out = []
    if simple:
        out.append([])
        if abs(dz) > 1e-6 and abs(dx) > 1e-6:
            A = [[(xb, za)]] + [[(xb - sg * abs(dz) * c, za)] for c in (1.0, 2.0) if abs(dz) * c < abs(dx)]
            B = [[(xa, zb)]] + [[(xa + sg * abs(dz) * c, zb)] for c in (1.0, 2.0) if abs(dz) * c < abs(dx)]
            out += A + B if keep == "a" else B + A
        return out
    for a1 in (2.0 * R, 0.7 * R, 4.0 * R):
        for c in (1.0, 2.0):
            if a1 + abs(dz) * c < abs(dx) - 0.5 * R:
                out += [[(xb - sg * (a1 + abs(dz) * c), za), (xb - sg * a1, zb)], [(xa + sg * a1, za), (xa + sg * (a1 + abs(dz) * c), zb)]]
    for zt in sorted(zgrid, key=lambda t: abs(t - za) + abs(t - zb)):
        if abs(zt - za) < 1e-6 or abs(zt - zb) < 1e-6: continue
        out.append([(xa, zt), (xb, zt)])
        a1 = 2.0 * R; u = abs(za - zt); v = abs(zb - zt)
        if 2 * a1 + u + v < abs(dx): out.append([(xa + sg * a1, za), (xa + sg * (a1 + u), zt), (xb - sg * (a1 + v), zt), (xb - sg * a1, zb)])
        if u + v < abs(dx): out.append([(xa + sg * u, zt), (xb - sg * v, zt)])
        if a1 + v < abs(dx): out.append([(xa, zt), (xb - sg * (a1 + v), zt), (xb - sg * a1, zb)])
        if a1 + u < abs(dx): out.append([(xa + sg * a1, za), (xa + sg * (a1 + u), zt), (xb, zt)])
    return out

def candidates(ea, eb, od, R, nplanes=5):
    """polylines from end a to end b (generator)"""
    pitch = od + 0.1; zgrid = [11.6 + pitch * k for k in range(int((61.0 - 11.6) / pitch))]
    def lead(e, zl): return list(e["lead"]) + ([(*e["pre"], zl)] if "pre" in e else []) + ([(e["x"], e["y0"], zl)] if e["kind"] == "pad" else [])
    def ez(e): return lane_z(e, od) if e["kind"] == "pad" else e["z"]
    za, zb = ez(ea), ez(eb); la, lb = lead(ea, za), lead(eb, zb)
    def rng(e):                                                   # plane y range one end can turn into directly
        if e["kind"] == "conn": return (e["y0"] + R, -85.6)
        if e["kind"] == "pad": return (-119.0, e["y0"] - 2 * R)
        if e["kind"] == "mf": return (-119.0, e["y0"] - R)
        return (e["y0"], e["y0"])
    (a0, a1), (b0, b1) = rng(ea), rng(eb); lo, hi = max(a0, b0), min(a1, b1)
    def planes(lo, hi, near_hi):
        if hi < lo - 1e-9: return []
        n = min(nplanes, int((hi - lo) / pitch) + 1); return [(hi - pitch * k) if near_hi else (lo + pitch * k) for k in range(n)]
    one = planes(lo, hi, near_hi=(ea["kind"] != "conn" and eb["kind"] != "conn"))
    keep = "b" if ea["kind"] == "conn" else "a" if abs(ea["x"] - eb["x"]) > 70.0 else "b"   # a long run stays at the pad lane's height
    if ea["kind"] == "pad" and eb["kind"] == "conn" and abs(ea["x"] - eb["x"]) > 70.0:
        # far pad field (A2) -> X1: run at lane height in a plane south of the board edge (it crosses no lane there), then one
        # ramp up and north into the connector's plane, east of the cavities
        sg = 1.0 if ea["x"] > eb["x"] else -1.0
        for p in one:
            for q in [-96.0 - pitch * k for k in range(4)]:
                for m_ in (0.5, 6.0, 12.0):
                    for span in (16.0, 24.0, 32.0):
                        x2 = eb["x"] + sg * (2 * R + m_)
                        yield la + [(ea["x"], q, za), (x2 + sg * span, q, za), (x2, p, zb), (eb["x"], p, zb)] + lb[::-1]
    for simple in (True, False):
        for p in one:
            for m in mids(ea["x"], za, eb["x"], zb, R, zgrid, simple, keep):
                yield la + [(ea["x"], p, za)] + [(x, p, z) for x, z in m] + [(eb["x"], p, zb)] + lb[::-1]
    if not one or "mf" in (ea["kind"], eb["kind"]):               # C-loop at the end that cannot reach the other end's plane (end b = the far end)
        if ea["kind"] in ("mf", "pad") and eb["kind"] in ("conn", "splice"): ea, eb, la, lb, za, zb, flip = eb, ea, lb, la, zb, za, True
        else: flip = False
        (a0, a1), (b0, b1) = rng(ea), rng(eb)
        for p in planes(a0, a1, False):
            for q in planes(b0, min(b1, p - 2 * R), True)[:4]:
                for zv in sorted(zgrid, key=lambda t: abs(t - zb)):
                    if abs(zv - zb) < 2 * R: continue
                    for m in mids(ea["x"], za, eb["x"], zv, R, zgrid, True, "b"):
                        pts = la + [(ea["x"], p, za)] + [(x, p, z) for x, z in m] + [(eb["x"], p, zv), (eb["x"], q, zv), (eb["x"], q, zb)] + lb[::-1]
                        yield pts[::-1] if flip else pts

def nail(e, od):
    """the straight end piece of a wire that is not placed yet"""
    if e["kind"] == "conn": a = np.array(e["lead"][0]); b = np.array([e["x"], e["y0"], e["z"]])
    elif e["kind"] == "mf": a = np.array(e["lead"][0]); b = np.array([e["x"], e["y0"], e["z"]])
    elif e["kind"] == "pad": a = np.array(e["lead"][0]); b = a + np.array([0, 0, lane_z(e, od) - a[2]])
    elif e["kind"] == "splice": a, b = np.array(e["lead"][0]), np.array(e["lead"][1])
    else: return np.zeros((0, 3))
    n = max(2, int(np.linalg.norm(b - a) / STEP)); return a + (b - a) * (np.arange(n + 1) / n)[:, None]

def plan(G, field, hand=None, order=None, log=print):
    T = HP.initial(G); rows = {r["Wire ID"]: r for r in HP.read_rows()}; L = Loom(field); E = {}; hand = hand or {}
    for k_, y_ in HP.SPLICE["y"].items():                          # the CAN splice bodies
        x0 = HP.SPLICE["x"] - HP.SPLICE["L"] / 2; L.set_obs("_" + k_, [(x0 + 0.5 * i, y_, HP.SPLICE["z"]) for i in range(int(HP.SPLICE["L"] / 0.5) + 1)], HP.SPLICE["d"] / 2)
    for w, d in T.items():
        if w in hand: d["pts"] = hand[w]
        if d["kind"] == "cable" or w in hand: E[w] = None
        else:
            ea, eb = end_info(G, rows[w], d["pts"], True), end_info(G, rows[w], d["pts"], False); E[w] = None if "fixed" in (ea["kind"], eb["kind"]) else (ea, eb)
        if E[w] is None: L.place(w, d["pts"], d["od"])               # rule / hand path: placed as it is
        else: L.set_obs(w, np.concatenate([nail(E[w][0], d["od"]), nail(E[w][1], d["od"])]), d["od"] / 2)
    for w in [w for w in T if E[w] is None]:
        r = L.check(w, T[w]["pts"], T[w]["od"], T[w]["rmul"], who=True)
        if r: L.why[w] = "rule path: " + r
    todo = [w for w in (order or sorted(T)) if E.get(w)] + [w for w in sorted(T) if E[w] and w not in (order or [])]
    for w in todo:
        d = T[w]; n = 0; got = None; tally = {}
        for pts in candidates(E[w][0], E[w][1], d["od"], d["rmul"] * d["od"]):
            n += 1; r = L.check(w, pts, d["od"], d["rmul"], who=n <= 40)
            if r is None: got = pts; break
            tally[r] = tally.get(r, 0) + 1
        if got: L.place(w, got, d["od"])
        else: L.why[w] = f"no shape in {n} tries: " + "; ".join(f"{k} x{v}" for k, v in sorted(tally.items(), key=lambda t: -t[1])[:7])
    return T, L

if __name__ == "__main__":
    VAR = sys.argv[1]; OUT = os.path.join(os.environ["RUN_DIR"], VAR); m = json.load(open(os.path.join(OUT, "meta.json"))); G = HP.G_from_meta(m)
    import harness_loom_data as HD
    T, L = plan(G, Field(OUT), hand=HD.hand(G), order=HD.order(G))
    for w, why in sorted(L.why.items()): print(w, why)
    routes = {w: L.path[w] for w in T if w in L.path and not T[w]["fixed"]}
    json.dump(dict(note="made by harness_comb_v2c.py (deterministic loom builder); do not edit by hand", routes=routes), open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "harness_routes_v2c.json"), "w"), indent=0)
    print("placed", len(L.path), "of", len(T), "open", len(L.why), "total length", round(sum(samples(L.path[w], T[w]["rmul"] * T[w]["od"])[3] for w in L.path)))
