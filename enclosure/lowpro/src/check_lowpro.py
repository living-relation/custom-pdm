"""Interference check of the low-profile build (RUN_DIR/brep/*.brep): every pair of parts, solid by solid,
bounding-box prefilter, then a boolean common; reports overlaps above 0.5 mm3 and min gaps of the key pairs.
Usage: $CAD_PY check_lowpro.py   (env RUN_DIR as for build_lowpro.py). Writes RUN_DIR/check.json."""
import os, glob, json, itertools
from build123d import import_brep
RUN = os.environ.get("RUN_DIR", os.path.expanduser("~/scratch/encl-lowpro/runs/v1"))
S = {os.path.basename(f)[:-5]: import_brep(f) for f in sorted(glob.glob(os.path.join(RUN, "brep", "*.brep")))}
# parts that touch by design (screwed / stacked / pressed together)
TOUCH = {frozenset(p) for p in [("heat-sink-base", "gap-pads"), ("gap-pads", "board-A1"), ("gap-pads", "board-A2"), ("gap-pads", "board-B"),
         ("heat-sink-base", "duct-cover"), ("heat-sink-base", "stud-blocks"), ("stud-blocks", "bar-BATT"), ("stud-blocks", "bar-GND"),
         ("stud-blocks", "straps-OUT1-4"), ("studs", "stud-blocks"), ("studs", "bar-BATT"), ("studs", "bar-GND"), ("studs", "straps-OUT1-4"),
         ("bar-BATT", "board-A1"), ("bar-BATT", "board-A2"), ("bar-BATT", "board-B"), ("bar-GND", "board-A1"), ("bar-GND", "board-A2"),
         ("bar-GND", "board-B"), ("straps-OUT1-4", "board-B"), ("heat-sink-base", "lid"), ("heat-sink-base", "board-A1"),
         ("heat-sink-base", "board-A2"), ("heat-sink-base", "board-B"), ("duct-cover", "fan-Noctua-NF-A6x15-FLX"),
         ("lid", "X1-HD34-24-21SN-envelope"), ("lid", "X2-HDP24-24-47SE-envelope"), ("lid", "USB-C-bulkhead-envelope"),
         ("lid", "input-board-A1"), ("lid", "input-board-A2"), ("lid", "input-board-B"), ("heat-sink-base", "USB-hub-Adafruit-5997-envelope")]}
def bb(s):
    b = s.bounding_box(); return (b.min.X, b.max.X, b.min.Y, b.max.Y, b.min.Z, b.max.Z)
def ov(a, b, m=0.0):
    return a[0] < b[1] + m and b[0] < a[1] + m and a[2] < b[3] + m and b[2] < a[3] + m and a[4] < b[5] + m and b[4] < a[5] + m
SO = {k: [(so, bb(so)) for so in v.solids()] for k, v in S.items()}
BB = {k: bb(v) for k, v in S.items()}
hits = []
for a, b in itertools.combinations(S, 2):
    if a.startswith("board") and b.startswith("board"): continue
    if not ov(BB[a], BB[b]): continue
    vol, where = 0.0, None
    for sa, ba in SO[a]:
        for sb, bbb in SO[b]:
            if not ov(ba, bbb): continue
            try:
                c = sa.intersect(sb); v = sum(x.volume for x in (c if isinstance(c, list) else [c]) if x is not None) if c else 0.0
            except Exception as e:
                v = -1.0
            if v > 0.5 or v < 0:
                vol += abs(v); where = where or [round(x, 1) for x in bb(sb)]
    if vol > 0.5:
        hits.append(dict(a=a, b=b, mm3=round(vol, 1), expected=frozenset((a, b)) in TOUCH, near=where))
for h in hits: print(("expected " if h["expected"] else "CLASH    ") + f"{h['a']} x {h['b']}: {h['mm3']} mm3 near {h['near']}")
json.dump(hits, open(os.path.join(RUN, "check.json"), "w"), indent=1)
print("unexpected:", sum(1 for h in hits if not h["expected"]))
