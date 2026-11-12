"""print the bounding box of every part BREP of a build: bbox_parts.py F1 [name-filter]"""
import os, sys, glob
from build123d import import_brep
VAR = sys.argv[1]; FLT = sys.argv[2] if len(sys.argv) > 2 else ""
for f in sorted(glob.glob(os.path.join(os.environ["RUN_DIR"], VAR, "brep", "*.brep"))):
    n = os.path.basename(f)[:-5]
    if FLT not in n: continue
    b = import_brep(f).bounding_box()
    print(f"{n:45s} x {b.min.X:7.1f} {b.max.X:7.1f}  y {b.min.Y:7.1f} {b.max.Y:7.1f}  z {b.min.Z:6.1f} {b.max.Z:6.1f}")
