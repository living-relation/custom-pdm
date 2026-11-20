"""3D model of the D2 load-dump TVS (DO-218AB / DO-218AC, Vishay SM8S; Bourns SM8S-Q, Panjit SM8H-AU) for the board STEPs.

usage (WSL, handbuilt-cad venv: build123d 0.13):  ~/.venvs/handbuilt-cad/bin/python tools/d2_model.py <out.step> [...]

Drawn from the MAXIMUM package dimensions of Vishay doc 98229 rev 23-Jan-2026 page 5 (so clearance checks are
conservative): plastic body 13.7 x 10.5 x 5.0 mm (x -7.95 .. 5.75), metal heat-sink base 10.3 x 9.3 mm, lead 3.0 wide,
0.7 thick, 3.5 high at the body end, tip at x 7.75 (15.7 overall; data sheet 15.0-16.0). The maker's own CAD sits behind the Ultra Librarian login (BACKLOG).
Frame = the footprint tools/d2_tvs.py writes (origin = middle of the 15.30 mm land pattern, lead at +x, z = 0 on the
board's top surface). Three solids: body, heat-sink base, lead.
"""
import sys

from build123d import Box, Location, Compound, export_step, Color

body = Box(13.7, 10.5, 5.0 - 0.1).moved(Location((-7.75 + 13.7 / 2 - 0.2, 0, 0.1 + (5.0 - 0.1) / 2)))   # x -7.95 .. 5.75
base = Box(10.3, 9.3, 0.1).moved(Location((-7.65 + 10.3 / 2, 0, 0.05)))                                    # x -7.65 .. 2.65
foot = Box(2.3, 3.0, 0.7).moved(Location((5.75 + 2.3 / 2 - 0.3, 0, 0.35)))                                 # x 5.45 .. 7.75
riser = Box(0.7, 3.0, 3.5).moved(Location((7.75 - 0.35, 0, 3.5 / 2)))
lead = foot.fuse(riser)
body.label, base.label, lead.label = "body", "heatsink", "lead"
body.color, base.color, lead.color = Color(0.15, 0.15, 0.15), Color(0.8, 0.8, 0.82), Color(0.8, 0.8, 0.82)
part = Compound(label="D_DO-218AB_Vishay_SM8S", children=[body, base, lead])
for out in sys.argv[1:]:
    export_step(part, out)
    print("wrote", out)
