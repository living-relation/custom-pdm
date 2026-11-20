"""Print bounding boxes / solid counts of the downloaded vendor STEP models (orientation check)."""
import os, glob
from build123d import import_step
V = os.environ["VENDOR"]
for f in sorted(glob.glob(os.path.join(V, "**", "*.st*p"), recursive=True)):
    s = import_step(f); b = s.bounding_box()
    print(os.path.basename(f), len(s.solids()), [round(v, 2) for v in (b.min.X, b.max.X, b.min.Y, b.max.Y, b.min.Z, b.max.Z)])
