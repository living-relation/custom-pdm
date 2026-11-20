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
RUN = os.path.join(os.environ["RUN_DIR"], VAR); PD = os.path.join(RUN, "xref", "Parts"); OUT = os.path.join(RUN, "drawings")
os.makedirs(OUT, exist_ok=True)
meta = json.load(open(os.path.join(RUN, "meta.json")))
V2B = datetime.date(2026, 11, 13)
GEN = ["BREAK SHARP EDGES 0.2-0.4 x 45 DEG UNLESS NOTED.", "INSIDE CORNERS: CUTTER RADIUS ALLOWED WHERE NOT MODELLED.",
       "THREADED HOLES ARE MODELLED AT TAP-DRILL SIZE; THREAD AS NOTED.", "MODEL: build_v2c.py (build123d). THE STEP FILE GOVERNS ALL UNDIMENSIONED GEOMETRY."]
JOBS = [
    (f"CPDM-ENC-101-{VAR}", "HEAT SINK / BASE " + VAR, "6061-T6 ALUMINIUM", "C",
     ["v2c: counterbores 8.0; fan wall holes 0.5 lower, notched; fins joined to the fan wall",
      "feet now separate (CPDM-ENC-112/113), M3 foot taps; pedestals 3.14 (gap pad 15 %); fan wall 6.0 (fan screws M3 x 16)"],
     ["LID SCREWS: 4.5 THRU, CBORE 8.0 x 5 FROM BELOW (x12).", "M3x0.5 TAP 6 DEEP IN THE 6.0 BOARD BOSSES (TAP DRILL 2.5 x 8).",
      "FOOT MOUNTS: 6.6 THRU (x4), BOLT-THROUGH; M3x0.5 TAP 4.5 DEEP, DRILL 2.5 x 6 FROM BELOW (x8).", "FAN WALL 6.0: M3x0.5 TAP THRU (x8), 28.0 THRU WITH 12 WIDE NOTCH TO THE FIN TIPS (x2), CENTRES Z -23.5 - SIDE SETUP.",
      "FIN ROOTS: CORNER RADIUS OF THE CUTTER (R0.5 BULL-NOSE) ALLOWED.", "FINISH: TBD (CLEAR ANODISE ASSUMED; MASK PEDESTAL TOPS).",
      "PEDESTALS (x7) 3.14 ABOVE THE PLATE TOP: GAP PADS CPDM-ENC-110-1..4 (1.016 FREE) COMPRESS TO 0.86 UNDER THE BOARDS."]),
    ("CPDM-ENC-112", "FOOT SW / NE", "6061-T6 ALUMINIUM", "A", [],
     ["6.6 THRU (M6 BOLT-THROUGH, CAR MOUNT).", "3.4 THRU, CBORE 6.5 TO 7.5 BELOW THE TOP FACE (x2) FOR M3 x 12 ISO 4762.", "FIT AFTER THE LID SCREWS (THE FOOT COVERS THE CORNER LID SCREW AREA)."]),
    ("CPDM-ENC-113", "FOOT SE / NW", "6061-T6 ALUMINIUM", "A", [],
     ["6.6 THRU (M6 BOLT-THROUGH, CAR MOUNT).", "3.4 THRU, CBORE 6.5 TO 7.5 BELOW THE TOP FACE (x2) FOR M3 x 12 ISO 4762.", "8.0 x 1 DEEP POCKET IN THE TOP FACE CLEARS THE LID SCREW HEAD (SE).", "FIT AFTER THE LID SCREWS."]),
    ("CPDM-ENC-104", "COPPER BAR BATT+", "C110 COPPER", "A", "", ["6.6 THRU (x3) AT THE M6 TERMINALS.", "11.0 THRU AT THE STANDOFF PASS-THROUGHS (INSULATING SLEEVE).", "INSULATING FILM UNDER THE BAR (ASSEMBLY)."]),
    ("CPDM-ENC-105", "COPPER BAR GND", "C110 COPPER", "A", "", ["6.6 THRU (x3) AT THE M6 TERMINALS.", "11.0 THRU AT THE STANDOFF PASS-THROUGHS (INSULATING SLEEVE)."]),
    ("CPDM-ENC-106", "COPPER TERMINAL BOSS M6", "C110 COPPER, HEX BAR AF13", "A", "", ["M6x1 TAP 10 DEEP BOTH ENDS (TAP DRILL 5.0 x 12 TOP / 10 BOTTOM)."]),
    ("CPDM-ENC-107", "COPPER OFFSET RISER, LOW (OUT2 / OUT4)", "C110 COPPER", "B", "v2c: seat 8.5 (was 7.52), foot R3.75, R0.5 root, drill through",
     ["SEAT COLUMN AXIS 8.50 FROM THE FOOT-HOLE AXIS.", "4.5 THRU AT THE FOOT (M4 x 6 INTO THE REDCUBE).", "M4x0.7 TAP 8 DEEP IN THE SEAT (TAP DRILL 3.3 THRU).", "COLUMN ROOT R0.5 (BULL-NOSE CORNER RADIUS)."]),
    ("CPDM-ENC-108", "COPPER OFFSET RISER, HIGH (OUT1 / OUT3)", "C110 COPPER", "B", "v2c: seat 8.5 (was 8.19), foot R3.75, R0.5 root",
     ["SEAT COLUMN AXIS 8.50 FROM THE FOOT-HOLE AXIS.", "4.5 THRU AT THE FOOT (M4 x 6 INTO THE REDCUBE).", "M4x0.7 TAP 8 DEEP IN THE SEAT (TAP DRILL 3.3 x 10).", "COLUMN ROOT R0.5 (BULL-NOSE CORNER RADIUS)."]),
    ("CPDM-ENC-109", "OUT1-4 RISER CARRIER", "G10 / FR4 GLASS-EPOXY, 3/4 IN PLATE", "B", "v2c: key slots / pockets follow the 8.5 risers; web 1.8",
     ["KEY SLOTS AND LUG POCKETS FOLLOW THE 8.5 RISERS (SEE STEP).", "ALL FEATURES FROM THE TOP; FLIP AND FACE TO THICKNESS.", "3.4 THRU, CBORE 6.5 x 3.2 (x2) FOR M3 x 8.", "CARBIDE TOOLS, DUST EXTRACTION (GLASS-EPOXY)."]),
    ("CPDM-ENC-102", "LID", "MJF PA12", "B", "revD: USB-C cut-out 18.5 / flats 16.5 for the CnLinko LP-16-C05SX-02-101 (Dan)", ["MJF PA12 FROM THE STEP; WALLS 3.0, DRAFT 6 DEG.", "HEAT-SET INSERTS ruthex RX-M4x8.1 IN THE 5.6 BOSS BORES (x12).", "TE D-FLAT PANEL CUT-OUTS 43.08 / FLAT PER TE SPEC 0425-021-0000 (x2); USB-C CUT-OUT 18.5 BETWEEN FLATS 16.5 (CnLinko LP-16-C05SX-02-101)."], "printed"),
    ("CPDM-ENC-103", "INPUT DECK", "MJF PA12", "A", "", ["MJF PA12 FROM THE STEP.", "M3 HEAT-SET INSERTS IN THE 4.0 BOSS BORES (x6), PN TBD."], "printed"),
]
res = {}
for job in JOBS:
    pn, title, mat, rev, why, notes = job[:6]; proc = job[6] if len(job) > 6 else "machined"
    step = os.path.join(PD, pn + ".stp"); rl = os.path.join(PD, pn + ".REVLOG.md")
    if os.path.exists(rl): os.remove(rl)
    whys = why if isinstance(why, list) else ([why] if why else [])
    new = pn in ("CPDM-ENC-112", "CPDM-ENC-113")                           # revD: new parts, Rev A today
    revs.add_release(rl, "A", "Initial", date=None if new else V2B, title=pn)   # v2b release (PR #46) / new part
    for L_, w_ in zip("BC", whys): revs.add_release(rl, L_, w_, title=pn)    # v2c (B), revD restructure (C)
    spec = dict(file=step, pn=pn, title=title, material=mat, process=proc, notes=notes + (GEN if proc == "machined" else GEN[3:]), project="custom-pdm enclosure v2c")
    if rev == "B": spec["rev_marks"] = [dict(rev="B", note=1)]   # DRAWING-RULES 33: triangle at the changed notes
    if rev == "C": spec["rev_marks"] = [dict(rev="B", note=1), dict(rev="B", note=4), dict(rev="C", note=3), dict(rev="C", note=7)]
    try:
        part.make_part(spec, os.path.join(OUT, pn + ".pdf"), os.path.join(OUT, pn + ".dxf"), os.path.join(OUT, pn + "_preview"))
        ck = os.path.join(OUT, pn + ".checks.json")
        res[pn] = dict(rev=rev, ok=json.load(open(ck)).get("ok") if os.path.exists(ck) else None)
    except Exception as e:
        res[pn] = dict(rev=rev, error=str(e)[:300])
    print(pn, res[pn], flush=True)
json.dump(res, open(os.path.join(OUT, "drawings.json"), "w"), indent=1)
