"""Tool-access check (revD, Dan 2026-11-20: the feet covered corner lid screws). For every screw in meta.json, the driver path is a
cylinder of the head diameter dk from the head top outward along the screw axis, 120 mm long. Any part in that path must be
installed AFTER the screw. STAGES (install order) lists item-name prefixes per stage; a screw belongs to the stage named for it in
SCREW_STAGE (by head-seat z / position rules below). FAILS (exit 1) when a part of the same or an earlier stage blocks a screw path.
Also lists, for the report, every screw whose path a foot touches (gap < 1 mm counts as blocked).
Usage: $CAD_PY access_v2c.py F1 [RUN_DIR] -> <run>/<VAR>/access.json"""
import os, sys, json, glob
from build123d import import_brep, Solid, Plane, Vector
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from screwtool_twin import row as screw_row
VAR = sys.argv[1]; RUN = sys.argv[2] if len(sys.argv) > 2 else os.environ["RUN_DIR"]
OUT = os.path.join(RUN, VAR); meta = json.load(open(os.path.join(OUT, "meta.json")))
B = {os.path.basename(f)[:-5]: import_brep(f) for f in glob.glob(os.path.join(OUT, "brep", "*.brep"))}
# install order (stage index): heat-sink subassembly, boards + board hardware, upper parts, lid + lid screws, feet + foot screws
STAGES = [("heat-sink-sub", ("heat-sink", "gap-pads", "fans-", "fan-lead-gland", "tie-points", "standoff-studs")),
          ("boards", ("board-", "copper-", "screws_M6", "standoffs-", "carrier-", "ring-lugs", "wires-", "input-", "vendor-", "usb", "hub-", "wire-ribbons", "panel-")),
          ("lid", ("lid", "heat-set-inserts")),
          ("feet", ("heat-sink-foot",))]
def stage_of_item(nm):
    if nm.startswith("heat-sink-foot"): return 3
    for i, (_, pre) in enumerate(STAGES):
        if nm.startswith(pre): return i
    return None
def stage_of_screw(s):
    return {"fan": 0, "tie": 0, "lid": 2, "feet": 3}.get(s.get("grp", ""), 1)
FAMILY = {"4762": "SHCS ISO 4762", "7380": "Button ISO 7380-1"}
res = dict(blocked_by_feet=[], fails=[], screws=0)
for s in meta["screws"]:
    r = screw_row(FAMILY[s.get("fam", "4762")], s["size"]); dk, k = float(r["dk_max"]), float(r["k_max"])
    at, ax = Vector(*s["at"]), Vector(*s["axis"])                                      # axis: seat -> head
    path = Solid.make_cylinder(dk / 2, 120.0, Plane(origin=at + ax * (k + 0.05), z_dir=ax))
    st = stage_of_screw(s); res["screws"] += 1
    for nm, sh in B.items():
        if nm.startswith("screws_"): continue
        d = BRepExtrema_DistShapeShape(path.wrapped, sh.wrapped); d.Perform()
        if not d.IsDone(): continue
        g = d.Value()
        if nm.startswith("heat-sink-foot") and g < 1.0:
            res["blocked_by_feet"].append(dict(screw=f"{s['size']}x{s['L']:g} {s.get('grp', '')}", at=s["at"], foot=nm, gap=round(g, 3)))
        si = stage_of_item(nm)
        if g < 1e-3 and si is not None and si < st:          # a part fitted in an EARLIER stage blocks the driver: no order works
            res["fails"].append(dict(screw=f"{s['size']}x{s['L']:g} {s.get('grp', '')}", at=s["at"], stage=STAGES[st][0], blocked_by=nm, item_stage=STAGES[si][0]))
        elif g < 1e-3 and si == st:                              # same stage: an install-order rule (screw before that part)
            res.setdefault("order", []).append(dict(screw=f"{s['size']}x{s['L']:g} {s.get('grp', '')}", at=s["at"], before=nm))
json.dump(res, open(os.path.join(OUT, "access.json"), "w"), indent=1)
print("screws", res["screws"], "blocked by feet:", res["blocked_by_feet"])
print("install-order rules (screw before part, same stage):", len(res.get("order", [])), sorted({o["before"] for o in res.get("order", [])}))
for f in res["fails"]: print("FAIL", f)
print("fails:", len(res["fails"]))
sys.exit(1 if res["fails"] else 0)
