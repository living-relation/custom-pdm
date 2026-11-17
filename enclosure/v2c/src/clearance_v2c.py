"""Clearance (near-miss) check for custom-pdm enclosure v2b (from Grok test2), complementing handbuilt-cad tools/checks/intf.py (which reports overlaps only):
every part pair, solid by solid, OCC BRepExtrema min distance + Boolean-common overlap volume. Parallel.
Usage: $CAD_PY clearance_v2b.py F1|F2   (RUN_DIR from the environment)"""
import os, json, itertools, glob, sys
from build123d import import_brep, Shape
from multiprocessing import Pool
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VAR = sys.argv[1]
OUT = os.path.join(os.environ.get("RUN_DIR", os.path.join(ROOT, "runs", "latest")), VAR)
REPORT_GAP = 2.5
S = SOL = None
def load():
    global S, SOL
    S = {os.path.basename(f)[:-5]: import_brep(f) for f in sorted(glob.glob(os.path.join(OUT, "brep", "*.brep")))}
    SOL = {k: [(so, BB(so)) for so in v.solids()] for k, v in S.items()}
class BB:
    def __init__(self, s):
        b = s.bounding_box(); self.xmin, self.ymin, self.zmin = b.min.X, b.min.Y, b.min.Z; self.xmax, self.ymax, self.zmax = b.max.X, b.max.Y, b.max.Z
def bbo(a, b, g):
    return not (a.xmax + g < b.xmin or b.xmax + g < a.xmin or a.ymax + g < b.ymin or b.ymax + g < a.ymin or a.zmax + g < b.zmin or b.zmax + g < a.zmin)
def vol(s):
    p = GProp_GProps(); BRepGProp.VolumeProperties_s(s, p); return p.Mass()
def work(t):
    a, b, i = t
    sa, ba = SOL[a][i]
    best = (1e9, None, None); inter = 0.0; where = None
    for sb, bb in SOL[b]:
        if not bbo(ba, bb, REPORT_GAP): continue
        d = BRepExtrema_DistShapeShape(sa.wrapped, sb.wrapped); d.Perform()
        if not d.IsDone(): continue
        dv = d.Value()
        if dv < 1e-4:
            c = BRepAlgoAPI_Common(sa.wrapped, sb.wrapped); c.Build()
            v = vol(c.Shape()) if c.IsDone() else -1
            if v > 1e-3:
                inter += v; cb = BB(Shape.cast(c.Shape()))
                where = (round(cb.xmin,1), round(cb.xmax,1), round(cb.ymin,1), round(cb.ymax,1), round(cb.zmin,1), round(cb.zmax,1))
        if dv < best[0]:
            p1 = d.PointOnShape1(1); p2 = d.PointOnShape2(1)
            best = (dv, (round(p1.X(),1), round(p1.Y(),1), round(p1.Z(),1)), (round(p2.X(),1), round(p2.Y(),1), round(p2.Z(),1)))
    return a, b, best, inter, where
if __name__ == "__main__":
    load()
    tasks = []
    BBX = {k: BB(v) for k, v in S.items()}
    for a, b in itertools.combinations(S, 2):
        if not bbo(BBX[a], BBX[b], REPORT_GAP): continue
        if len(SOL[a]) > len(SOL[b]): a, b = b, a      # iterate the part with fewer solids
        for i, (sa, ba) in enumerate(SOL[a]):
            if bbo(ba, BBX[b], REPORT_GAP): tasks.append((a, b, i))
    print(len(tasks), "tasks", flush=True)
    agg = {}
    with Pool(int(os.environ.get("NPROC", "10")), initializer=load) as pool:
        for n, (a, b, best, inter, where) in enumerate(pool.imap_unordered(work, tasks)):
            r = agg.setdefault((a, b), dict(a=a, b=b, min_gap=1e9, at_a=None, at_b=None, overlap_mm3=0.0, overlap_bbox=None))
            if best[0] < r["min_gap"]: r.update(min_gap=round(best[0], 3), at_a=best[1], at_b=best[2])
            if inter > 0: r["overlap_mm3"] = round(r["overlap_mm3"] + inter, 3); r["overlap_bbox"] = where
            if n % 50 == 0: print("done", n, flush=True)
    res = [r for r in agg.values() if r["min_gap"] < REPORT_GAP or r["overlap_mm3"] > 0]
    res.sort(key=lambda r: (r["overlap_mm3"] == 0, r["min_gap"]))
    json.dump(dict(variant=VAR, report_gap=REPORT_GAP, pairs=res), open(os.path.join(OUT, "check.json"), "w"), indent=1)
    for r in res: print(r)
