"""Masses of the machined / printed v2b parts from the build BREPs (densities: Al 6061 2.70, MJF PA12 1.01, Cu C110 8.94 g/cm3).
Usage: $CAD_PY mass_v2b.py F1|F2   (RUN_DIR from the environment)"""
import os, sys, glob
from build123d import import_brep
VAR = sys.argv[1]
B = os.path.join(os.environ["RUN_DIR"], VAR, "brep")
RHO = {"heat-sink": 2.70, "lid": 1.01, "input-deck": 1.01, "copper-bar-BATT": 8.94, "copper-bar-GND": 8.94,
       "copper-boss-M6-BATT-GND": 8.94, "copper-risers-OUT1-4": 8.94, "carrier-G10-OUT1-4": 1.85, "flow-cone-PA12": 1.01}
tot = 0.0
for n, r in RHO.items():
    f = os.path.join(B, n + ".brep")
    if not os.path.exists(f):
        print(n, "missing"); continue
    s = import_brep(f); v = s.volume / 1000.0; m = v * r; tot += m
    print(f"{n:28s} {v:9.1f} cm3 {m:8.0f} g")
print(f"{'total (these parts)':28s} {'':13s} {tot:8.0f} g")
