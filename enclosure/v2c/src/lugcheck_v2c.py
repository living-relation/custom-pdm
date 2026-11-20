"""Bare-metal clearance checks for the custom-pdm enclosure (v2c). Usage: $CAD_PY lugcheck_v2c.py F1 [RUN_DIR]  (RUN_DIR from env
or the 2nd argument, so the same check runs on an older build, e.g. v2b in ~/scratch/encl-v2b/runs). Writes <run>/<VAR>/lugcheck.json.
1) OUT1-4 stack (e1a, Dan 2026-11-13): min 3-D distance between each ring lug and (a) every other lug, (b) every screw that is not
   its own (own lug screw + own riser foot screw are same-net), (c) every copper riser that is not its own.
2) HEAD rule (v2c, 2026-11-16): every socket-head screw head against EVERY bare-metal feature beside or above its bearing face,
   SAME NET INCLUDED. Bare metal on the same net still needs machining / assembly room: a cutter corner radius at a column root,
   a counterbore wall, a neighbouring head. Measured: head solid (top k of the screw) vs bare-metal solids clipped to the
   half-space beyond the bearing face + 0.05. Rule: gap >= 0.5 mm (DIN 974-1 M4 counterbore 8.0 round a dk 7.0 head = 0.5;
   fillets / corner radii that the part really gets are modelled, so they count). Insulated wire and plastic are not bare metal
   (Dan 2026-11-13: insulated wire may touch plastic)."""
import os, sys, json, glob, csv
from build123d import import_brep, Solid, Plane, Compound
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
VAR = sys.argv[1]
RUN = sys.argv[2] if len(sys.argv) > 2 else os.environ["RUN_DIR"]
OUT = os.path.join(RUN, VAR)
RULE = 0.5; TOL = 1e-3
meta = json.load(open(os.path.join(OUT, "meta.json")))
BR = {os.path.basename(f)[:-5]: f for f in glob.glob(os.path.join(OUT, "brep", "*.brep"))}
B = lambda n: import_brep(BR[n])
def dist(a, b):
    d = BRepExtrema_DistShapeShape(a.wrapped, b.wrapped); d.Perform(); return d.Value()
def bb(s):
    b = s.bounding_box(); return (b.min.X, b.min.Y, b.min.Z), (b.max.X, b.max.Y, b.max.Z)
lugs = B("ring-lugs-OUT1-4").solids()
ris = [s for n in sorted(BR) if n.startswith("copper-risers-OUT1-4") for s in B(n).solids()]
SOL = {n: B(n).solids() for n in BR}
scr = [(n, s) for n in BR if n.lower().startswith("screws_") for s in SOL[n]]
seats = meta["OUT_SEAT"]; names = list(seats.keys())
def cxy(s):
    (x0, y0, z0), (x1, y1, z1) = bb(s); return ((x0 + x1) / 2, (y0 + y1) / 2, z1)
def lug_key(s):
    c = cxy(s); return min(names, key=lambda k: (c[0] - seats[k][0]) ** 2 + (c[1] - seats[k][1]) ** 2 + (c[2] - seats[k][2]) ** 2)
lugk = [lug_key(s) for s in lugs]
def riser_key(s):
    (x0, y0, z0), (x1, y1, z1) = bb(s)
    return min(names, key=lambda k: min((meta["OUTT"][k][0] - (x0 + x1) / 2) ** 2 + (meta["OUTT"][k][1] - (y0 + y1) / 2) ** 2, 1e9) + 0 * z1)
def own(k, s, r=3.0):
    x, y, _ = cxy(s); sx, sy, _ = seats[k]; tx, ty = meta["OUTT"][k]
    return (abs(x - sx) < r and abs(y - sy) < r) or (abs(x - tx) < r and abs(y - ty) < r)
res = {"lug_lug": [], "lug_screw": [], "lug_riser": []}
for i, a in enumerate(lugs):
    k = lugk[i]
    for j in range(i + 1, len(lugs)): res["lug_lug"].append((k, lugk[j], round(dist(a, lugs[j]), 2)))
    near = [s for (_, s) in scr if abs(cxy(s)[0] - 36) < 30 and abs(cxy(s)[1] + 33) < 30 and not own(k, s)]
    if near:
        dd = sorted((round(dist(a, s), 2), [round(c, 1) for c in cxy(s)]) for s in near)
        res["lug_screw"].append((k, dd[0]))
    sk = seats[k]
    res["lug_riser"].append((k, round(min(dist(a, r) for r in ris if not (abs(bb(r)[1][2] - sk[2]) < 0.6 and min(abs(cxy(r)[0] - sk[0]), 99) < 6 and abs(cxy(r)[1] - sk[1]) < 6)), 2)))
for k, v in res.items(): print(k, v)
# ---- 2) head rule ----
ROWS = [r for r in csv.DictReader(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "screw_dimensions.csv"))) if r["family"] == "SHCS ISO 4762"]
METAL = ("copper", "ring-lugs", "screws_", "standoffs", "standoff-studs", "heat-sink", "heat-set", "panel-nuts", "panel-washers")
metal = [(n, s) for n in BR if n.startswith(METAL) for s in SOL[n]]     # same solid objects as scr, so 'is' finds the screw itself
def big(lo, hi):
    lo = [max(v, -1e3) for v in lo]; hi = [min(v, 1e3) for v in hi]
    return Solid.make_box(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2], Plane(origin=tuple(lo)))
def slab_ext(s, i, v, h=0.3):
    lo = [-1e3] * 3; hi = [1e3] * 3; lo[i] = v - h / 2; hi[i] = v + h / 2
    r = s.intersect(big(lo, hi))
    if not r: return 0.0
    r = Compound(list(r)) if isinstance(r, list) else r
    (a0, a1, a2), (b0, b1, b2) = bb(r); e = [b0 - a0, b1 - a1, b2 - a2]; e[i] = 0; return max(e)
heads = []
for n, s in scr:
    (x0, y0, z0), (x1, y1, z1) = bb(s); ext = [x1 - x0, y1 - y0, z1 - z0]; i = ext.index(max(ext))
    dk = max(e for j, e in enumerate(ext) if j != i)
    row = min(ROWS, key=lambda r: abs(float(r["dk_max"]) - dk))
    if abs(float(row["dk_max"]) - dk) > 0.3: continue                       # not a socket-head screw (stud, csk ...)
    k = float(row["k_max"]); lo_, hi_ = [x0, y0, z0][i], [x1, y1, z1][i]
    head_hi = slab_ext(s, i, hi_ - 0.4) > slab_ext(s, i, lo_ + 0.4)
    he = hi_ if head_hi else lo_; bear = he - k if head_hi else he + k
    lo = [x0 - 1, y0 - 1, z0 - 1]; hi = [x1 + 1, y1 + 1, z1 + 1]
    if head_hi: lo[i] = bear
    else: hi[i] = bear
    head = s.intersect(big(lo, hi)); head = Compound(list(head)) if isinstance(head, list) else head
    zl = [-1e3] * 3; zh = [1e3] * 3
    if head_hi: zl[i] = bear + 0.05
    else: zh[i] = bear - 0.05
    zone = big(zl, zh)
    best = (1e9, None)
    for (m, ms) in metal:
        if ms is s: continue
        (a0, a1, a2), (b0, b1, b2) = bb(ms)
        if a0 > x1 + 3 or b0 < x0 - 3 or a1 > y1 + 3 or b1 < y0 - 3 or a2 > z1 + 3 or b2 < z0 - 3: continue
        c = ms.intersect(zone)
        if not c: continue
        c = Compound(list(c)) if isinstance(c, list) else c
        if not c.solids(): continue
        d = dist(head, c)
        if d < best[0]: best = (d, m)
    if best[1] is None: continue
    heads.append(dict(screw=n, size=row["size"], at=[round((x0 + x1) / 2, 2), round((y0 + y1) / 2, 2), round(he, 2)],
                      nearest=best[1], gap=round(best[0], 3), ok=best[0] >= RULE - TOL))
heads.sort(key=lambda h: h["gap"])
bad = [h for h in heads if not h["ok"]]
print(f"head rule (>= {RULE} mm, same net included): {len(bad)} finding(s) of {len(heads)} heads with bare metal nearby")
for h in heads[:12]: print("  ", "FAIL" if not h["ok"] else "ok  ", h)
json.dump(dict(variant=VAR, run=RUN, rule_mm=RULE, lug=res, head_findings=bad, heads=heads), open(os.path.join(OUT, "lugcheck.json"), "w"), indent=1)
