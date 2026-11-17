"""Compare a v2c build with the v2b build it replaces (WSL ~/scratch/encl-v2b/runs/<VAR>/brep, the converted copies that
survived): per part, volume, bounding box and the volume of the symmetric difference (what moved / changed).
Usage: $CAD_PY compare_v2b.py F1 [v2b_run_dir]   (RUN_DIR = the v2c runs). Writes <run>/<VAR>/compare_v2b.json."""
import os, sys, glob, json
from build123d import import_brep, Compound
VAR = sys.argv[1]
OLD = os.path.join(sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser("~/scratch/encl-v2b/runs"), VAR, "brep")
NEW = os.path.join(os.environ["RUN_DIR"], VAR, "brep")
REN = {"copper-risers-OUT1-4": ["copper-risers-OUT1-4-low", "copper-risers-OUT1-4-high"],
       "screws_SSH-M3-0.5_x_8": ["screws_ISO4762-M3x8"], "screws_SSH-M4-0.7_x_12": ["screws_ISO4762-M4x12"],
       "screws_SSH-M4-0.7_x_6": ["screws_ISO4762-M4x6"], "screws_SSH-M4-0.7_x_8": ["screws_ISO4762-M4x8"],
       "screws_SSH-M6-1_x_10": ["screws_ISO4762-M6x10"], "screws_SSH-M6-1_x_16": ["screws_ISO4762-M6x16"]}
def load(d, names):
    ss = [import_brep(os.path.join(d, n + ".brep")) for n in names if os.path.exists(os.path.join(d, n + ".brep"))]
    return None if not ss else (ss[0] if len(ss) == 1 else Compound([s for x in ss for s in x.solids()]))
def bb(s):
    b = s.bounding_box(); return [round(v, 2) for v in (b.min.X, b.max.X, b.min.Y, b.max.Y, b.min.Z, b.max.Z)]
res = []; done = set()
for f in sorted(glob.glob(os.path.join(OLD, "*.brep"))):
    n = os.path.basename(f)[:-5]; nn = REN.get(n, [n]); done.update(nn)
    a = import_brep(f); b = load(NEW, nn)
    if b is None: res.append(dict(part=n, status="not in v2c")); continue
    r = dict(part=n, v2c=nn, vol_v2b=round(a.volume, 1), vol_v2c=round(b.volume, 1), bbox_v2b=bb(a), bbox_v2c=bb(b))
    small = len(a.solids()) < 40 and len(b.solids()) < 40
    if small:
        try:
            r["sym_diff_mm3"] = round(a.cut(b).volume + b.cut(a).volume, 1)
        except Exception as e:
            r["sym_diff_mm3"] = f"err {str(e)[:40]}"
    r["same"] = abs(r["vol_v2b"] - r["vol_v2c"]) < 0.5 and r["bbox_v2b"] == r["bbox_v2c"] and (not small or (isinstance(r.get("sym_diff_mm3"), float) and r["sym_diff_mm3"] < 1.0))
    res.append(r)
for f in sorted(glob.glob(os.path.join(NEW, "*.brep"))):
    n = os.path.basename(f)[:-5]
    if n not in done: res.append(dict(part=n, status="new in v2c", vol_v2c=round(import_brep(f).volume, 1)))
json.dump(res, open(os.path.join(os.environ["RUN_DIR"], VAR, "compare_v2b.json"), "w"), indent=1)
for r in res:
    if r.get("same"): print("same    ", r["part"])
for r in res:
    if not r.get("same"): print("CHANGED ", {k: v for k, v in r.items() if k not in ("same",)})
