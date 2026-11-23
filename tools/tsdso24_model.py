"""Best-guess 3D body of the Infineon PG-TSDSO-24 package (board B U8-U11, BTS70012-1ESP) for the board STEPs.

usage (WSL, handbuilt-cad venv: build123d 0.13):
    ~/.venvs/handbuilt-cad/bin/python tools/tsdso24_model.py <out.step> [--measure <PG-TSDSO-14_INF.step>]

Why: upstream dingoPDM-Max points these four footprints at a file on its author's own disk
(C:/Users/cgrant/Dropbox/.../PG-TSDSO-24-32.step), so the board STEP had no body for them (docs/order-readiness.md
section 5). Infineon's product page offers no plain STEP download for the package (looked 2026-11-22), and the package
drawing in the data sheet (BTS70012-1ESP Rev. 1.21, 2024-07-29, figure 40) is a picture without machine-readable
numbers. So this is a LABELLED BEST GUESS, drawn conservatively (clearance checks only):
  * body 3.9 mm wide (the footprint's F.Fab outline, TSDSO-24.kicad_mod: x -1.97 .. 1.93) x 8.65 mm long (ASSUMED:
    24 leads at 0.65 mm pitch + the end margins of the same family's 14-lead body, 4.9 mm for 7 leads);
  * leads to x +-3.0 (lead span 6.0 mm: the footprint's 1.31 mm pads end at +-3.51), 0.3 wide, 0.2 thick;
  * exposed pad 2.77 x 6.4 mm (the footprint's pad 25);
  * height: the top of Infineon's own PG-TSDSO-14 STEP (hardware/board-b-max/Models/PG-TSDSO-14_INF.step, the same
    package family on U23-U26), measured by --measure: 1.15 mm is used when no file is given (ASSUMED family maximum).
Frame = the footprint's (origin = centre, long axis on y, z = 0 on the board top). Solids: body, pad, 24 leads.
"""
import sys

from build123d import Box, Location, Compound, export_step, import_step, Color

args = sys.argv[1:]
top = 1.15
if "--measure" in args:
    i = args.index("--measure")
    bb = import_step(args[i + 1]).bounding_box()
    top = round(bb.max.Z, 3)
    print(f"PG-TSDSO-14 maker model: x {bb.min.X:.2f} .. {bb.max.X:.2f}, y {bb.min.Y:.2f} .. {bb.max.Y:.2f}, z {bb.min.Z:.3f} .. {bb.max.Z:.3f}")
    del args[i:i + 2]
BW, BL, STANDOFF = 3.9, 8.65, 0.05
body = Box(BW, BL, top - STANDOFF).moved(Location((0, 0, STANDOFF + (top - STANDOFF) / 2)))
pad = Box(2.77, 6.4, STANDOFF).moved(Location((0, 0, STANDOFF / 2)))
leads = []
for k in range(12):
    y = (k - 5.5) * 0.65
    for sx in (-1, 1):
        leads.append(Box(3.0 - BW / 2, 0.3, 0.2).moved(Location((sx * (BW / 2 + (3.0 - BW / 2) / 2), y, 0.1))))
body.label, pad.label = "body (best guess)", "exposed pad"
body.color, pad.color = Color(0.15, 0.15, 0.15), Color(0.8, 0.8, 0.82)
for n, ld in enumerate(leads):
    ld.label, ld.color = f"lead{n + 1}", Color(0.8, 0.8, 0.82)
part = Compound(label="PG-TSDSO-24_bestguess", children=[body, pad] + leads)
for out in args:
    export_step(part, out)
    print(f"wrote {out}: body {BW} x {BL} x top {top} mm")
