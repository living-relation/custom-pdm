"""Harness check (revF): every wire / cable solid of CPDM-HAR-200 against every other part of the build, against the other wires,
and against the box's free space.
Rule (cad.md): an insulated wire may TOUCH plastic and other wires; it may not pass THROUGH a part.
What the model is for (coordinator, 2026-11-21): it shows where the loom runs, that it fits, its lengths, and that nothing is
impossible. Real wires are flexible and lie against each other, so the model does not try to keep every wire off every other.
FAILS (exit 1) on:
  1. a wire through a part: the wire shrunk by DIP mm on its radius still overlaps the part above TOL (mm3), and the pair is not
     ALLOWED (a wire inside its own end part: the fan leads in the cord grip and in their sleeve, a spliced wire in its splice,
     a T5-T8 wire in its lug barrel). Dips up to DIP are listed (wire_part_touch), not failed;
  2. wire on wire: every pair whose centre lines come nearer than r1 + r2 is COUNTED and LISTED (wire_wire_pairs). Only a gross
     pile-up fails: two wires that share more than half the smaller diameter over more than PILE_LEN mm of run outside the
     fan-out zones (ZONE mm round either wire's two ends: connector rears, pad rows, housings, splices);
  3. a wire outside the box's free space. The placed parts' surfaces are voxelised (1 mm), the air outside the closed box
     is flood-filled from a corner, and a wire centre-line point in that outside air fails. The fan leads may be below the plate,
     inside the sink's footprint and above the feet's underside (they run in the fin bay to the cord grip);
  4. a bend below the wire's radius (3 x OD; USB cables 4 x OD).
Usage: $CAD_PY wirecheck_v2c.py F1   (RUN_DIR)  -> <run>/<VAR>/wirecheck.json"""
import os, sys, json, glob, math
import numpy as np
from build123d import import_brep
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
import harness_paths_v2c as HP
VAR = sys.argv[1]; RUN = os.environ["RUN_DIR"]; OUT = os.path.join(RUN, VAR)
TOL = 0.05; DIP = 0.3; PILE_LEN = 15.0; ZONE = 25.0       # mm3, mm
FAN = ("W061", "W062", "W063", "W064")
SKIP = ("harness-", "wire-ribbons", "usb-cables", "vendor-plug")
def allowed(w, nm, d):
    if w in FAN and nm in ("fan-lead-gland", "fan-lead-sleeve", "splices-fan-solder"): return True
    if nm.startswith("splices-CAN") and any(s in d["desc"] for s in ("SP1.", "SP2.")): return True
    if nm.startswith("splices-fan") and any(s in d["desc"] for s in ("SP3.", "SP4.")): return True
    if nm == "ring-lugs-T5-8" and "B-T" in d["desc"]: return True
    if nm == "gh-housings-GHR-12V-S" and "-J1." in d["desc"]: return True      # a GH link wire in its own housing (drawn block, no cavities)
    return False
def bb(s): b = s.bounding_box(); return (b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z)
def hit(a, b, g=0.0): return not (a[3] + g < b[0] or b[3] + g < a[0] or a[4] + g < b[1] or b[4] + g < a[1] or a[5] + g < b[2] or b[5] + g < a[2])
def vol(a, b):
    c = BRepAlgoAPI_Common(a.wrapped, b.wrapped); c.Build()
    if not c.IsDone(): return -1.0
    p = GProp_GProps(); BRepGProp.VolumeProperties_s(c.Shape(), p); return p.Mass()
def table(): return json.load(open(os.path.join(OUT, "harness_paths.json")))
T = W = P = None
def load():
    global T, W, P
    T = table(); W = {}
    for w, d in T.items(): s = HP.solid(d); W[w] = (s, bb(s), HP.solid(dict(d, od=d["od"] - 2 * DIP)))
    P = {}
    for f in sorted(glob.glob(os.path.join(OUT, "brep", "*.brep"))):
        nm = os.path.basename(f)[:-5]
        if nm.startswith(SKIP): continue
        P[nm] = [(so, bb(so)) for so in import_brep(f).solids()]
def work(w):
    s, b, core = W[w]; res = []
    for nm, sols in P.items():
        near = [so for so, sb in sols if hit(b, sb)]; v = sum(max(vol(s, so), 0.0) for so in near)
        if v > TOL: res.append((w, nm, round(v, 2), round(sum(max(vol(core, so), 0.0) for so in near), 2)))   # full wire, wire shrunk by DIP
    return res, []
def wire_wire(T):
    """centre-line distances (0.25 mm points): pairs nearer than r1 + r2 -> [(a, b, deepest overlap mm, length mm of the longest
    run deeper than half the smaller diameter outside the fan-out zones)]"""
    from scipy.spatial import cKDTree
    S = {}
    for w, d in T.items():
        P = centre_line(d, 0.25); S[w] = (P, np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]), d["od"] / 2, cKDTree(P))
    ws = sorted(S); out = []
    for i, a in enumerate(ws):
        Pa, sa, ra, ta = S[a]
        for b_ in ws[i + 1:]:
            Pb, sb, rb, _ = S[b_]
            if (Pa.min(0) > Pb.max(0) + 3).any() or (Pb.min(0) > Pa.max(0) + 3).any(): continue
            dd, _ = ta.query(Pb); ov = ra + rb - dd
            if not (ov > 0.02).any(): continue
            ends = np.array([Pa[0], Pa[-1], Pb[0], Pb[-1]]); zone = (np.linalg.norm(Pb[:, None, :] - ends[None], axis=2) < ZONE).any(1)
            g = np.where((ov > min(ra, rb)) & ~zone)[0]; run = 0.0
            if len(g): run = max(float(sb[r_[-1]] - sb[r_[0]]) for r_ in np.split(g, np.where(np.diff(g) > 1)[0] + 1))
            out.append((a, b_, round(float(ov.max()), 2), round(run, 1)))
    return out
def centre_line(d, step=0.5):
    out = []
    for s in d["segs"]:
        if s[0] == "L":
            a, b = np.array(s[1]), np.array(s[2]); n = max(1, int(np.linalg.norm(b - a) / step)); out.append(a + (b - a) * (np.arange(n + 1) / n)[:, None])
        else:
            p1, p2, c = np.array(s[1]), np.array(s[2]), np.array(s[4]); v1, v2 = p1 - c, p2 - c; th = math.acos(max(-1.0, min(1.0, float(v1 @ v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))))
            n = max(2, int(s[5] * th / step)); q = np.arange(n + 1) / n
            out.append(c + (np.sin((1 - q) * th)[:, None] * v1 + np.sin(q * th)[:, None] * v2) / max(math.sin(th), 1e-9))
    return np.concatenate(out)
def free_space(T):
    """wire centre-line points in the air OUTSIDE the closed box -> {wire: count}; also how the box closed"""
    import harness_comb_v2c as HR
    from scipy import ndimage
    pts, _, _ = HR.surface_points(OUT, spacing=0.6, zmin=-2.0); m = json.load(open(os.path.join(OUT, "meta.json")))
    lo = pts.min(0) - 3.0; n = np.ceil((pts.max(0) + 3.0 - lo)).astype(int) + 1; shell = np.zeros(n, bool); ix = np.floor(pts - lo).astype(int); shell[ix[:, 0], ix[:, 1], ix[:, 2]] = True
    floor = int(math.floor(-2.0 - lo[2])) + 1; shell[:, :, :floor] = True          # the plate closes the box from below (points are kept above z -2 only)
    for grow in (0, 1):
        sh = ndimage.binary_dilation(shell, iterations=grow) if grow else shell
        lab, k = ndimage.label(~sh); outside = lab[0, 0, n[2] - 1]; inside_pts = 0; bad = {}; tot = 0
        for w, d in T.items():
            c = centre_line(d); c = c[c[:, 2] > 0.5] if w in FAN else c
            if not len(c): continue
            j = np.floor(c - lo).astype(int); ok = ((j >= 0) & (j < n)).all(1); l = np.where(ok, lab[np.clip(j[:, 0], 0, n[0] - 1), np.clip(j[:, 1], 0, n[1] - 1), np.clip(j[:, 2], 0, n[2] - 1)], outside)
            nb = int((l == outside).sum()); tot += len(c)
            if nb: bad[w] = nb
        if sum(bad.values()) < 0.5 * tot: break                                    # the box is closed at this voxel shell
    sb = m["sink_bbox"] if "sink_bbox" in m else None; low = {}
    for w in FAN:
        c = centre_line(T[w]); c = c[c[:, 2] <= 0.5]; zmin = -(m["P"]["plate_t"] + m["P"]["fin_h"] + m["P"]["foot_h"])
        x0, x1 = (m["P"]["edge_clear"] * -1.0, 1e9) if sb is None else (sb[0], sb[3]) if len(sb) == 6 else (-10.0, 1e9)
        nb = int(((c[:, 2] < zmin) | (c[:, 0] < -10.0) | (c[:, 0] > 270.2) | (c[:, 1] < -130.0) | (c[:, 1] > 10.0)).sum())
        if nb: low[w] = nb
    return bad, low, dict(voxel_mm=1.0, shell_grown=grow, closed=sum(bad.values()) < 0.5 * tot, components=int(k))
if __name__ == "__main__":
    import multiprocessing                                # spawn: a forked OCC process can hang on a lock taken before the fork
    T = table()
    with multiprocessing.get_context("spawn").Pool(int(os.environ.get("NPROC", "12")), initializer=load) as pool: out = pool.map(work, sorted(T), chunksize=2)
    parts = [x for r, _ in out for x in r]; wires = wire_wire(T); gross = [x for x in wires if x[3] > PILE_LEN]
    fails = [x for x in parts if x[3] > TOL and not allowed(x[0], x[1], T[x[0]])]
    touch = [x for x in parts if x[3] <= TOL and not allowed(x[0], x[1], T[x[0]])]
    outside, low, fs = free_space(T)
    tight = {w: d["r_over_od"] for w, d in T.items() if d["r_over_od"] < d["rmul"] - 1e-6}
    rep = dict(solids=len(T), rows=sum(len(d["rows"]) for d in T.values()), wire_part_overlaps=parts, fails=fails, wire_part_touch=touch, wire_wire_pairs=wires, wire_wire_gross=gross,
               outside_free_space=outside, fan_leads_outside_fin_bay=low,
               free_space=fs, bend_below_min=tight, total_length_mm=round(sum(d["length"] for d in T.values()), 0), tol=dict(part_mm3=TOL, dip_mm=DIP, pile_len_mm=PILE_LEN, zone_mm=ZONE))
    json.dump(rep, open(os.path.join(OUT, "wirecheck.json"), "w"), indent=1)
    by = {}
    for w, nm, v, vc in fails: by.setdefault(nm, []).append(f"{w}:{vc:g}")
    for nm, ws in sorted(by.items()): print("FAIL wire through part", nm, len(ws), " ".join(ws)[:300])
    print("wire dips into a part up to", DIP, "mm (listed, not failed):", len(touch), " ".join(f"{w}/{nm}:{v:g}" for w, nm, v, vc in touch)[:400])
    print("wire-on-wire pairs:", len(wires), "(all in wirecheck.json); deepest:", " ".join(f"{a}/{b}:{v:g}" for a, b, v, r in sorted(wires, key=lambda t: -t[2])[:12]))
    print("gross pile-ups (FAIL):", len(gross), " ".join(f"{a}/{b}:{r:g}mm" for a, b, v, r in gross))
    print("outside the free space:", outside, low, fs)
    nfail = len(fails) + len(gross) + len(outside) + len(low) + len(tight) + (0 if fs["closed"] else 1)
    print("solids", rep["solids"], "rows", rep["rows"], "allowed", len(parts) - len(fails), "bend below min:", tight, "FAILS:", nfail)
    sys.exit(1 if nfail else 0)
