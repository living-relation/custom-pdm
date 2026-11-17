"""Manufacturing drawings of the made v2c parts, generated FROM THE MODELS with the handbuilt-cad drawing engine
(drawing/part.py: B-rep hidden-line removal, no hidden lines, rev log top right, initials from ~/.drawing-initials).
Usage: $CAD_PY drawings_v2c.py F1   (RUN_DIR; HANDBUILT_CAD = handbuilt-cad checkout, default ~/projects/handbuilt-cad)
Reads <run>/<VAR>/xref/parts/<PN>.stp; writes <PN>.REVLOG.md beside each STEP (model rev log = source of truth,
DRAWING-RULES 12) and <run>/<VAR>/drawings/<PN>.pdf / .dxf / preview PNG / .checks.json.
Rev letters (DRAWING-RULES 1-4): a model's letter counts its merged PRs that changed it. v2b (PR #46, 13/11/26) = A for every
part; v2c (this PR) changes the heat sink (counterbores, fan wall), the risers and the carrier = B; the others stay A.
Never edit a drawing by hand: change build_v2c.py, rebuild, re-run this (DRAWING-RULES 6)."""
import os, sys, json, datetime
VAR = sys.argv[1] if len(sys.argv) > 1 else "F1"
HB = os.environ.get("HANDBUILT_CAD", os.path.expanduser("~/projects/handbuilt-cad"))
for d in ("drawing", "tools/render", "tools/checks", "tools"): sys.path.insert(0, os.path.join(HB, d))
import part, revs
RUN = os.path.join(os.environ["RUN_DIR"], VAR); PD = os.path.join(RUN, "xref", "parts"); OUT = os.path.join(RUN, "drawings")
os.makedirs(OUT, exist_ok=True)
meta = json.load(open(os.path.join(RUN, "meta.json")))
V2B = datetime.date(2026, 11, 13)
GEN = ["BREAK SHARP EDGES 0.2-0.4 x 45 DEG UNLESS NOTED.", "INSIDE CORNERS: CUTTER RADIUS ALLOWED WHERE NOT MODELLED.",
       "THREADED HOLES ARE MODELLED AT TAP-DRILL SIZE; THREAD AS NOTED.", "MODEL: build_v2c.py (build123d). THE STEP FILE GOVERNS ALL UNDIMENSIONED GEOMETRY."]
JOBS = [
    (f"CPDM-ENC-101-{VAR}", "HEAT SINK / BASE " + VAR, "6061-T6 ALUMINIUM", "B",
     "v2c: lid-screw counterbores 8.0 (DIN 974-1); fan wall holes 0.5 lower",
     ["M3x0.5 TAP 6 DEEP IN THE 6.0 BOARD BOSSES (TAP DRILL 2.5 x 8).", "LID SCREWS: 4.5 THRU, CBORE 8.0 x 5 FROM BELOW (x12).",
      "FEET: 6.6 THRU (x4), BOLT-THROUGH MOUNTING.", "FAN WALL: M3x0.5 TAP THRU 3 WALL (x8), 28.0 THRU (x2) - SIDE SETUP.",
      "FIN ROOTS: CORNER RADIUS OF THE CUTTER (R0.5 BULL-NOSE) ALLOWED.", "FINISH: TBD (CLEAR ANODISE ASSUMED; MASK PEDESTAL TOPS)."]),
    ("CPDM-ENC-104", "COPPER BAR BATT+", "C110 COPPER", "A", "", ["6.6 THRU (x3) AT THE M6 TERMINALS.", "11.0 THRU AT THE STANDOFF PASS-THROUGHS (INSULATING SLEEVE).", "INSULATING FILM UNDER THE BAR (ASSEMBLY)."]),
    ("CPDM-ENC-105", "COPPER BAR GND", "C110 COPPER", "A", "", ["6.6 THRU (x3) AT THE M6 TERMINALS.", "11.0 THRU AT THE STANDOFF PASS-THROUGHS (INSULATING SLEEVE)."]),
    ("CPDM-ENC-106", "COPPER TERMINAL BOSS M6", "C110 COPPER, HEX BAR AF13", "A", "", ["M6x1 TAP 10 DEEP BOTH ENDS (TAP DRILL 5.0 x 12 TOP / 10 BOTTOM)."]),
    ("CPDM-ENC-107", "COPPER OFFSET RISER, LOW (OUT2 / OUT4)", "C110 COPPER", "B", "v2c: seat 8.5 from the foot hole (was 7.52), R0.5 root",
     ["4.5 THRU AT THE FOOT (M4 x 6 INTO THE REDCUBE).", "M4x0.7 TAP 8 DEEP IN THE SEAT (TAP DRILL 3.3 x 10).", "COLUMN ROOT R0.5 (BULL-NOSE CORNER RADIUS)."]),
    ("CPDM-ENC-108", "COPPER OFFSET RISER, HIGH (OUT1 / OUT3)", "C110 COPPER", "B", "v2c: seat 8.5 from the foot hole (was 8.19), R0.5 root",
     ["4.5 THRU AT THE FOOT (M4 x 6 INTO THE REDCUBE).", "M4x0.7 TAP 8 DEEP IN THE SEAT (TAP DRILL 3.3 x 10).", "COLUMN ROOT R0.5 (BULL-NOSE CORNER RADIUS)."]),
    ("CPDM-ENC-109", "OUT1-4 RISER CARRIER", "G10 / FR4 GLASS-EPOXY, 3/4 IN PLATE", "B", "v2c: key slots and lug pockets follow the 8.5 risers",
     ["ALL FEATURES FROM THE TOP; FLIP AND FACE TO THICKNESS.", "3.4 THRU, CBORE 6.5 x 3.2 (x2) FOR M3 x 8.", "CARBIDE TOOLS, DUST EXTRACTION (GLASS-EPOXY)."]),
]
res = {}
for pn, title, mat, rev, why, notes in JOBS:
    step = os.path.join(PD, pn + ".stp"); rl = os.path.join(PD, pn + ".REVLOG.md")
    if os.path.exists(rl): os.remove(rl)
    revs.add_release(rl, "A", "Initial", date=V2B, title=pn)               # v2b release (PR #46)
    if rev == "B": revs.add_release(rl, "B", why, title=pn)                # this release (v2c)
    spec = dict(file=step, pn=pn, title=title, material=mat, process="machined", notes=notes + GEN, project="custom-pdm enclosure v2c")
    try:
        part.make_part(spec, os.path.join(OUT, pn + ".pdf"), os.path.join(OUT, pn + ".dxf"), os.path.join(OUT, pn + "_preview"))
        ck = os.path.join(OUT, pn + ".checks.json")
        res[pn] = dict(rev=rev, ok=json.load(open(ck)).get("ok") if os.path.exists(ck) else None)
    except Exception as e:
        res[pn] = dict(rev=rev, error=str(e)[:300])
    print(pn, res[pn], flush=True)
json.dump(res, open(os.path.join(OUT, "drawings.json"), "w"), indent=1)
