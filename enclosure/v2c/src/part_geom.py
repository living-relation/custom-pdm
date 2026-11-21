"""Geometry fingerprint of every part STEP of a build or release: solid count, bounding box (mm), volume (mm3), face count.
Usage: $CAD_PY part_geom.py <parts folder> <out.json>. fusion_v2c.verify_parts() compares each Fusion part design with it, and
bomcheck_v2c.py uses the solid count (one made part = one solid)."""
import os, sys, json, glob
from build123d import import_step
PD, OUT = sys.argv[1], sys.argv[2]
res = {}
for f in sorted(glob.glob(os.path.join(PD, "*.stp"))):
    s = import_step(f); b = s.bounding_box(); so = s.solids()
    res[os.path.basename(f)[:-4]] = dict(solids=len(so), faces=len(s.faces()), volume=round(sum(x.volume for x in so), 3),
                                         bbox=[round(v, 3) for v in (b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z)],
                                         bytes=os.path.getsize(f))
    print(os.path.basename(f), res[os.path.basename(f)[:-4]], flush=True)
json.dump(res, open(OUT, "w"), indent=1)
print("parts", len(res))
