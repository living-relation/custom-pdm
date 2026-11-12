"""List the tallest / lowest solids in the three board STEPs (board-local KiCad-STEP frame, board bottom Z=0)."""
import os
from build123d import import_step
REF = os.path.expanduser("~/scratch/encl-lowpro/work/reference/boards")
for fn in ("board-A.step", "board-B.step", "input-board.step"):
    s = import_step(os.path.join(REF, fn))
    bb = s.bounding_box()
    print("==", fn, "bbox", [round(v, 2) for v in (bb.min.X, bb.max.X, bb.min.Y, bb.max.Y, bb.min.Z, bb.max.Z)], "nsolids", len(s.solids()))
    rows = []
    for so in s.solids():
        b = so.bounding_box()
        rows.append((b.max.Z, b.min.Z, b.min.X, b.max.X, b.min.Y, b.max.Y))
    rows.sort(reverse=True)
    for r in rows[:30]:
        print("  ztop %.2f zbot %.2f x %.1f..%.1f y %.1f..%.1f" % r)
    lows = sorted([r for r in rows if r[1] < -0.3], key=lambda r: r[1])
    for r in lows[:10]:
        print("  BELOW ztop %.2f zbot %.2f x %.1f..%.1f y %.1f..%.1f" % r)
