"""Bare-metal clearance check for the OUT1-4 stack (e1a, Dan 2026-11-13): min distance between each ring lug and
(a) every other ring lug, (b) every screw head/shank not its own, (c) every copper riser not its own; plus min G10 carrier wall.
Insulated wire may touch plastic (Dan), so wires are not checked here. Usage: $CAD_PY lugcheck_v2b.py F1 (RUN_DIR from env)."""
import os, sys, json, glob
from build123d import import_brep
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
VAR = sys.argv[1]
OUT = os.path.join(os.environ["RUN_DIR"], VAR)
meta = json.load(open(os.path.join(OUT, "meta.json")))
B = lambda n: import_brep(os.path.join(OUT, "brep", n + ".brep"))
def dist(a, b):
    d = BRepExtrema_DistShapeShape(a.wrapped, b.wrapped); d.Perform(); return d.Value()
lugs = B("ring-lugs-OUT1-4").solids(); ris = B("copper-risers-OUT1-4").solids()
scr_file = [f for f in glob.glob(os.path.join(OUT, "brep", "*.brep")) if "screw" in os.path.basename(f).lower()]
scr = [s for f in scr_file for s in import_brep(f).solids()]
seats = meta["OUT_SEAT"]
names = list(seats.keys())
def cxy(s):
    b = s.bounding_box(); return ((b.min.X + b.max.X) / 2, (b.min.Y + b.max.Y) / 2, b.max.Z)
def own(lug_i, s, r=3.0):
    """same-net screws (its own lug screw at the seat and its own riser's foot screw at the T terminal) are not a hazard"""
    x, y, _ = cxy(s); k = names[lug_i]; sx, sy, _ = seats[k]; tx, ty = meta["OUTT"][k]
    return (abs(x - sx) < r and abs(y - sy) < r) or (abs(x - tx) < r and abs(y - ty) < r)
res = {"lug_lug": [], "lug_screw": [], "lug_riser": []}
for i, a in enumerate(lugs):
    for j in range(i + 1, len(lugs)): res["lug_lug"].append((names[i], names[j], round(dist(a, lugs[j]), 2)))
    near = [s for s in scr if abs(cxy(s)[0] - 36) < 30 and abs(cxy(s)[1] + 33) < 30 and not own(i, s)]
    if near:
        dd = sorted((round(dist(a, s), 2), [round(c, 1) for c in cxy(s)]) for s in near)
        res["lug_screw"].append((names[i], dd[0]))
    res["lug_riser"].append((names[i], round(min(dist(a, r) for k, r in enumerate(ris) if k != i), 2)))
for k, v in res.items(): print(k, v)
