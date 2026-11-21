"""custom-pdm enclosure v2c revF: the harness router. Relaxes the path table's first paths (harness_paths_v2c.initial) until
no wire passes through a part or through another wire and every bend keeps the wire's radius, and writes the result to
harness_routes_v2c.json (committed data, read by harness_paths_v2c.table).

Method (position-based relaxation, numpy):
  - a wire = its control polyline, filleted at its bend radius (the same curve the solids are swept along); its ends (the two
    points at each end: terminal + straight exit) are fixed; long legs get extra control points so the wire can bend;
  - parts = points sampled on every placed part's surface (the draft build's BREPs, 0.6 mm grid on the triangles) + the USB plug
    bodies of the path table; wires = points every 0.5 mm along the filleted curve;
  - each pass: a wire sample closer to a part point than radius + GAP_PART, or to another wire's sample than r1 + r2 + GAP_WIRE,
    is pushed out; the push goes to the control points that own the sample; a bend that does not fit its legs is straightened;
    control points are kept evenly spaced. Steps are capped at 0.4 mm so a wire cannot jump through a wall.
  - it stops when the smallest wire-wire and wire-part gaps are >= 0.1 mm and every bend fits; else it reports what is left.
The fan leads below the plate are not relaxed (rule path, side by side in the sleeve). wirecheck_v2c.py is the judge (exact solids).
Usage: $CAD_PY harness_route_v2c.py F1   (RUN_DIR of a DRAFT build: HARNESS_DRAFT=1 build_v2c.py)  -> <src>/harness_routes_v2c.json"""
import os, sys, json, glob, math, time
import numpy as np
from scipy.spatial import cKDTree
import harness_paths_v2c as HP
GAP_WIRE = 0.25; GAP_PART = 0.30; STEP = 0.5; CAP = 0.4
SKIP = ("harness-",)

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
            fb = face.bounding_box()
            if fb.max.Z < zmin: continue
            try: v, t = face.tessellate(0.05, 0.3)
            except Exception: v, t = [], []
            if not len(t): continue
            p = tri_points(np.array([(q.X, q.Y, q.Z) for q in v]), np.array(t), spacing); p = p[p[:, 2] > zmin]
            P.append(p.astype(np.float32)); I.append(np.full(len(p), n, np.int16))
    P = np.concatenate(P); I = np.concatenate(I); np.savez(cache, pts=P, item=I, names=np.array(names)); return P, I, names
def plug_points(tab, spacing=0.4):
    out = []; own = []
    for w, d in tab.items():
        for p in d.get("plugs", []):
            if p[0] == "box":
                x0, x1, y0, y1, z0, z1 = p[1:]; g = [np.arange(lo, hi + 1e-6, spacing) for lo, hi in ((x0, x1), (y0, y1), (z0, z1))]
                for ax in range(3):
                    o = [i for i in range(3) if i != ax]; A, B = np.meshgrid(g[o[0]], g[o[1]], indexing="ij")
                    for val in ((x0, y0, z0)[ax], (x1, y1, z1)[ax]):
                        q = np.zeros((A.size, 3)); q[:, ax] = val; q[:, o[0]] = A.ravel(); q[:, o[1]] = B.ravel(); out.append(q); own += [w] * len(q)
            else:
                a, b = np.array(p[1]), np.array(p[2]); u = (b - a) / np.linalg.norm(b - a); e1 = np.cross(u, [0.3, 0.5, 0.8]); e1 /= np.linalg.norm(e1); e2 = np.cross(u, e1)
                for s in np.arange(0, np.linalg.norm(b - a) + 1e-6, spacing):
                    for an in np.arange(0, 2 * math.pi, 0.3): out.append((a + u * s + p[3] / 2 * (math.cos(an) * e1 + math.sin(an) * e2))[None, :]); own.append(w)
    return (np.concatenate(out), own) if out else (np.zeros((0, 3)), [])

class Wire:
    def __init__(s, w, d):
        s.w = w; s.r = d["od"] / 2; s.R = d["rmul"] * d["od"]; s.P = np.array(d["pts"], float); nf = d["nfix"]; n = len(s.P)
        s.fix = np.zeros(n, bool); s.fix[:nf[0]] = True; s.fix[n - nf[1]:] = True; s.subdivide(max(3.0 * s.R, 6.0))
    def subdivide(s, lmax):
        P = [s.P[0]]; F = [s.fix[0]]
        for i in range(1, len(s.P)):
            L = np.linalg.norm(s.P[i] - s.P[i - 1]); stub = s.fix[i] and s.fix[i - 1]
            k = 1 if stub else int(math.ceil(L / lmax))
            for j in range(1, k): P.append(s.P[i - 1] + (s.P[i] - s.P[i - 1]) * j / k); F.append(False)
            P.append(s.P[i]); F.append(s.fix[i])
        s.P = np.array(P); s.fix = np.array(F)
    def fit(s):
        """per inner control point: 1.0 when its bend fits its two legs at the full radius, else the factor the radius would shrink by"""
        P = s.P; n = len(P); d = P[1:] - P[:-1]; Ls = np.linalg.norm(d, axis=1); u = d / Ls[:, None]
        tn = s.R * np.tan(np.arccos(np.clip((u[:-1] * u[1:]).sum(1), -1, 1)) / 2) if n > 2 else np.zeros(0); F = np.ones(max(n - 2, 0))
        a = np.concatenate([[0.0], tn]); b = np.concatenate([tn, [0.0]]); f = np.minimum(1.0, Ls * 0.999 / np.maximum(a + b, 1e-12))
        if n > 2: F = np.minimum(f[:-1], f[1:])
        return F
    def straighten(s, passes=6, k=0.5):
        """the bend radius wins over the pushes: control points whose bend does not fit are pulled towards their neighbours' mid-point"""
        for _ in range(passes):
            F = s.fit(); bad = np.zeros(len(s.P), bool); bad[1:-1] = F < 0.999
            if not bad.any(): return 0
            b2 = bad.copy(); b2[:-1] |= bad[1:]; b2[1:] |= bad[:-1]; b2 &= ~s.fix; lap = np.zeros_like(s.P); lap[1:-1] = (s.P[:-2] + s.P[2:]) / 2 - s.P[1:-1]; s.P[b2] += k * lap[b2]
        return int((s.fit() < 0.999).sum())
    def sample(s):
        P = s.P; n = len(P); d = P[1:] - P[:-1]; Ls = np.linalg.norm(d, axis=1); u = d / Ls[:, None]
        th = np.arccos(np.clip((u[:-1] * u[1:]).sum(1), -1, 1)) if n > 2 else np.zeros(0); tn = s.R * np.tan(th / 2); F = np.ones(max(n - 2, 0))
        for j in range(n - 1):
            a = tn[j - 1] if j > 0 else 0.0; b = tn[j] if j < n - 2 else 0.0
            if a + b > Ls[j] * 0.999:
                f = Ls[j] * 0.999 / (a + b)
                if j > 0: F[j - 1] = min(F[j - 1], f)
                if j < n - 2: F[j] = min(F[j], f)
        t = tn * F; X = []; A = []; B = []; WB = []
        for j in range(n - 1):
            t0 = t[j - 1] if j > 0 else 0.0; t1 = t[j] if j < n - 2 else 0.0; m = max(1, int(math.ceil((Ls[j] - t0 - t1) / STEP)))
            q = t0 + (Ls[j] - t0 - t1) * (np.arange(m + 1) / m); X.append(P[j] + u[j] * q[:, None]); A += [j] * (m + 1); B += [j + 1] * (m + 1); WB += list(q / Ls[j])
        for i in range(1, n - 1):
            if th[i - 1] < 1e-3: continue
            r = s.R * F[i - 1]; wh = u[i] - u[i - 1]; wh /= np.linalg.norm(wh); tg = u[i] + u[i - 1]; tg /= np.linalg.norm(tg); c = P[i] + wh * r / math.cos(th[i - 1] / 2)
            m = max(2, int(math.ceil(r * th[i - 1] / STEP))); an = (np.arange(1, m) / m - 0.5) * th[i - 1]
            X.append(c + r * (-np.cos(an)[:, None] * wh + np.sin(an)[:, None] * tg)); A += [i] * (m - 1); B += [i] * (m - 1); WB += [1.0] * (m - 1)
        s.F = F; return np.concatenate(X), np.array(A), np.array(B), np.array(WB)

def relax(tab, parts, iters=1500, log=print):
    wires = [Wire(w, d) for w, d in sorted(tab.items()) if not d["fixed"]]
    fixedw = [Wire(w, d) for w, d in sorted(tab.items()) if d["fixed"]]
    for fw in fixedw: fw.fix[:] = True
    allw = wires + fixedw; ptree = cKDTree(parts); rmax = max(w.r for w in allw); t0 = time.time(); stat = {}
    for it in range(iters):
        S = [w.sample() for w in allw]; X = np.concatenate([s[0] for s in S]); wid = np.concatenate([np.full(len(s[0]), k) for k, s in enumerate(S)])
        off = np.cumsum([0] + [len(w.P) for w in allw]); A = np.concatenate([s[1] + off[k] for k, s in enumerate(S)]); B = np.concatenate([s[2] + off[k] for k, s in enumerate(S)])
        WB = np.concatenate([s[3] for s in S]); rad = np.array([w.r for w in allw])[wid]; D = np.zeros_like(X); hit = np.zeros(len(X), bool)
        fx = np.concatenate([w.fix for w in allw]); free = ((1 - WB) * ~fx[A] + WB * ~fx[B]) > 0.5      # samples that mostly belong to movable control points (the gaps are measured there)
        dist, idx = ptree.query(X, distance_upper_bound=rmax + GAP_PART); m = dist < rad + GAP_PART
        if m.any():
            nrm = X[m] - parts[idx[m]]; nl = np.linalg.norm(nrm, axis=1); nl[nl < 1e-6] = 1e-6; D[m] += nrm / nl[:, None] * (rad[m] + GAP_PART - dist[m])[:, None]; hit |= m
        fm = free & np.isfinite(dist); pmin = float((dist - rad)[fm].min()) if fm.any() else 9.0
        pr = cKDTree(X).query_pairs(2 * rmax + GAP_WIRE, output_type="ndarray"); wmin = 9.0
        if len(pr):
            i, j = pr[:, 0], pr[:, 1]; k = wid[i] != wid[j]; i, j = i[k], j[k]; v = X[i] - X[j]; dl = np.linalg.norm(v, axis=1); need = rad[i] + rad[j] + GAP_WIRE - dl; k = need > 0
            fp = free[i] | free[j]
            if fp.any(): wmin = float((dl - rad[i] - rad[j])[fp].min())
            i, j, v, dl, need = i[k], j[k], v[k], dl[k], need[k]; dl[dl < 1e-6] = 1e-6; nv = v / dl[:, None] * (need / 2)[:, None]
            np.add.at(D, i, nv); np.add.at(D, j, -nv); hit[i] = True; hit[j] = True
        D *= 0.6
        NP = sum(len(w.P) for w in allw); num = np.zeros((NP, 3)); den = np.zeros(NP); h = np.nonzero(hit)[0]
        np.add.at(num, A[h], D[h] * (1 - WB[h])[:, None]); np.add.at(den, A[h], 1 - WB[h]); np.add.at(num, B[h], D[h] * WB[h][:, None]); np.add.at(den, B[h], WB[h])
        infeas = 0
        for k, w in enumerate(wires):
            n = len(w.P); mv = np.zeros((n, 3)); dn = den[off[k]:off[k + 1]]; ok = dn > 1e-9; mv[ok] = num[off[k]:off[k + 1]][ok] / dn[ok][:, None]
            lap = np.zeros((n, 3)); lap[1:-1] = (w.P[:-2] + w.P[2:]) / 2 - w.P[1:-1]; bad = np.zeros(n, bool); bad[1:-1] = w.F < 0.999; infeas += int(bad.sum())
            bad2 = bad.copy(); bad2[:-1] |= bad[1:]; bad2[1:] |= bad[:-1]; mv += lap * np.where(bad2, 0.35, 0.03)[:, None]
            tan = np.zeros((n, 3)); tan[1:-1] = w.P[2:] - w.P[:-2]; tl = np.linalg.norm(tan, axis=1); tl[tl < 1e-9] = 1.0; tan /= tl[:, None]
            la = np.zeros(n); la[1:-1] = (np.linalg.norm(w.P[2:] - w.P[1:-1], axis=1) - np.linalg.norm(w.P[1:-1] - w.P[:-2], axis=1)) / 2; mv += tan * (0.15 * la)[:, None]
            ml = np.linalg.norm(mv, axis=1); sc = np.minimum(1.0, CAP / np.maximum(ml, 1e-9)); mv *= sc[:, None]; mv[w.fix] = 0.0; w.P += mv; infeas += w.straighten() - int(bad.sum())
        stat = dict(iter=it, wire_gap_min=round(wmin, 3), part_gap_min=round(pmin, 3), bends_not_fitting=infeas, seconds=round(time.time() - t0))
        if it % 50 == 0: log(stat)
        if it > 30 and wmin >= 0.1 and pmin >= 0.1 and infeas == 0: break
    worst = {}
    if len(pr) and len(i):                                   # what is left: the closest wire pairs / the wires nearest a part
        gap = dl - rad[i] - rad[j]
        for q in np.argsort(gap)[:400]:
            if not (free[i[q]] or free[j[q]]): continue
            key = tuple(sorted((allw[wid[i[q]]].w, allw[wid[j[q]]].w))); worst.setdefault(key, round(float(gap[q]), 2))
    stat["closest_pairs"] = sorted(([k[0], k[1], g] for k, g in worst.items()), key=lambda t: t[2])[:25]
    near = {}
    for q in np.nonzero(m & free)[0]: near[allw[wid[q]].w] = min(near.get(allw[wid[q]].w, 9), round(float(dist[q] - rad[q]), 2))
    stat["nearest_part"] = sorted(near.items(), key=lambda t: t[1])[:25]
    return {w.w: [[round(float(c), 3) for c in p] for p in w.P] for w in wires}, stat

if __name__ == "__main__":
    VAR = sys.argv[1]; OUT = os.path.join(os.environ["RUN_DIR"], VAR); m = json.load(open(os.path.join(OUT, "meta.json")))
    tab = HP.table(HP.G_from_meta(m), strict=False, use_routes=os.environ.get("ROUTE_CONTINUE") == "1")
    P, I, names = surface_points(OUT); pp, _ = plug_points(tab); parts = np.concatenate([P.astype(float), pp]); print("part points", len(P), "plug points", len(pp), flush=True)
    routes, stat = relax(tab, parts, iters=int(os.environ.get("ROUTE_ITERS", "1500")), log=lambda s: print(s, flush=True))
    for w, pts in routes.items():
        d = dict(tab[w]); d["pts"] = pts; HP.finish(d)
        if d["rmin"] < d["rmul"] * d["od"] - 1e-6: stat.setdefault("tight_bends", []).append((w, d["r_over_od"]))
    json.dump(dict(note="made by harness_route_v2c.py from a draft build; do not edit by hand", report=stat, routes=routes), open(HP.ROUTEF, "w"), indent=0)
    print(json.dumps(stat)[:3000]); print("routes", len(routes), "->", HP.ROUTEF)
