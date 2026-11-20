"""Assembly drawing of the v2c enclosure with install-order sheets, generated FROM THE MODELS (handbuilt-cad drawing/asm.py:
B-rep hidden-line removal, BOM from the build's BOM CSV, balloons, exploded install steps with dotted lines, rev log top right).
Usage: $CAD_PY asm_drawing_v2c.py F1   (RUN_DIR; HANDBUILT_CAD = handbuilt-cad checkout, default ~/projects/handbuilt-cad)
Reads <run>/<VAR>/meta.json (placements), xref/Parts/<PN>.stp, BOM-v2c-<VAR>.csv; writes <run>/<VAR>/drawings/CPDM-ENC-100-<VAR>.pdf
(+ .checks.json, preview PNGs) and CPDM-ENC-100-<VAR>.REVLOG.md beside it.
Install order (access_v2c.py STAGES, Dan 2026-11-20): heat-sink subassembly (set-screw studs, gap pads, tie mounts, fans) ->
boards -> standoffs / copper / carrier -> input deck, hub, harness -> lid + lid screws -> feet + foot screws (the feet cover the
corner lid screws, so the lid screws go in first). Boards are drawn as their bare PCB (largest solid of the board STEP) so the
hidden-line pass stays tractable; every other part is its full model. Never edit the PDF: change the build, re-run this."""
import os, sys, json, csv, datetime
import numpy as np
VAR = sys.argv[1] if len(sys.argv) > 1 else "F1"
HB = os.environ.get("HANDBUILT_CAD", os.path.expanduser("~/projects/handbuilt-cad"))
for d in ("drawing", "tools/render", "tools/checks", "tools"): sys.path.insert(0, os.path.join(HB, d))
import asm, revs
from build123d import import_step, Location, Compound
from OCP.gp import gp_Trsf
from OCP.TopLoc import TopLoc_Location
RUN = os.path.join(os.environ["RUN_DIR"], VAR); PD = os.path.join(RUN, "xref", "Parts"); OUT = os.path.join(RUN, "drawings")
os.makedirs(OUT, exist_ok=True)
meta = json.load(open(os.path.join(RUN, "meta.json"))); PL = meta["placements"]
APN = meta["assembly"]["name"]
bom = list(csv.DictReader(open(os.path.join(RUN, f"BOM-{meta['rev']}-{VAR}.csv"), encoding="utf-8")))
def loc(m):
    t = gp_Trsf(); t.SetValues(m[0], m[1], m[2], m[3], m[4], m[5], m[6], m[7], m[8], m[9], m[10], m[11]); return Location(TopLoc_Location(t))
SHP = {}
def part_shape(pn):
    if pn not in SHP:
        s = import_step(os.path.join(PD, pn + ".stp"))
        if pn.startswith("CPDM-PCB-"): s = max(s.solids(), key=lambda x: x.volume)        # bare PCB (see docstring)
        SHP[pn] = s
    return SHP[pn]
INST = {nm: [part_shape(p["pn"]).moved(loc(m)) for m in p["m"]] for nm, p in PL.items()}   # meta item -> placed shapes
NO = {r["part_number"]: i + 1 for i, r in enumerate(bom)}
items = []
for r in bom:
    pn = r["part_number"]; shs = [s for nm, p in PL.items() if p["pn"] == pn for s in INST[nm]]
    items.append(dict(item=NO[pn], qty=int(r["qty"]), pn=pn, desc=r["name"], mat=(r.get("material") or "")[:28], shapes=shs,
                      primary=pn in ("CPDM-ENC-102", f"CPDM-ENC-101-{VAR}", "CPDM-ENC-112", "CPDM-ENC-113")))
def no(nm): return NO[PL[nm]["pn"]]
def pick(*pre): return [nm for nm in PL if nm.startswith(pre)]
def mv(names, vec):
    """custom moves: exactly the shapes of these meta items (a PN shared by two install steps moves only here)"""
    return [(no(nm), s, vec) for nm in names for s in INST[nm]]
fan_ax = np.mean([s["axis"] for s in meta["screws"] if s.get("grp") == "fan"], axis=0)
FAN = tuple(float(v) for v in fan_ax * 45.0); FANS = tuple(float(v) for v in fan_ax * 80.0)
SINK = [no("heat-sink")]; BOARDS = [no(nm) for nm in pick("board-")]
scr = lambda grp: [nm for nm in PL if nm.startswith("screws_") and nm.endswith("_" + grp)]
plain_m3x8 = [nm for nm in PL if nm == "screws_ISO4762-M3x8"]
steps = [
    dict(no=1, title="HEAT-SINK SUBASSEMBLY", subtitle="SET SCREWS 5.0 INTO THE BOSSES, GAP PADS, TIE MOUNTS, FANS + FAN SCREWS",
         base=SINK, custom=mv(pick("standoff-studs-"), (0, 0, 40)) + mv(pick("gap-pads-"), (0, 0, 22)) + mv(pick("tie-points"), (0, 0, 22))
         + mv(pick("fans-"), FAN) + mv(scr("fan"), FANS)),
    dict(no=2, title="BOARDS ON THE GAP PADS AND STUDS", subtitle="BOARD SCREWS M3 x 8 INTO THE SINK BOSSES",
         base=SINK, custom=mv(pick("board-"), (0, 0, 40)) + mv(scr("board"), (0, 0, 75))),
    dict(no=3, title="STANDOFFS, COPPER, RISERS, CARRIER, LUGS", subtitle="F-F STANDOFFS SPUN ONTO THE STUDS; M6 / M4 / M3 SCREWS",
         base=SINK + BOARDS, custom=mv(pick("standoffs-"), (0, 0, 30)) + mv(pick("copper-bar"), (0, 0, 55)) + mv(pick("copper-boss", "screws_M6"), (0, 0, 80))
         + mv(pick("copper-risers"), (0, 0, 45)) + mv(pick("carrier-"), (0, 0, 95)) + mv(pick("ring-lugs"), (0, 0, 115))
         + mv(pick("screws_ISO4762-M6", "screws_ISO4762-M4x6", "screws_ISO4762-M4x8", "screws_ISO4762-M3x6"), (0, 0, 135))),
    dict(no=4, title="INPUT DECK, INPUT BOARDS, HUB, CONNECTORS, HARNESS", subtitle="DECK SCREWS M3 x 8 INTO THE STANDOFFS",
         base=SINK + BOARDS, custom=mv(pick("input-deck"), (0, 0, 40)) + mv(pick("input-board", "vendor-J2"), (0, 0, 70)) + mv(plain_m3x8, (0, 0, 95))
         + mv(pick("vendor-hub", "hub-standoffs"), (0, 0, 40)) + mv(pick("vendor-X", "vendor-plug", "panel-", "usbc-"), (0, -60, 0))
         + mv(pick("wires-", "wire-ribbons", "usb-cables"), (0, 0, 60))),
    dict(no=5, title="LID (HEAT-SET INSERTS FITTED) AND LID SCREWS", subtitle="LID SCREWS M4 x 12 FROM BELOW - BEFORE THE FEET",
         base=SINK, custom=mv(pick("lid"), (0, 0, 110)) + mv(pick("heat-set-inserts"), (0, 0, 110)) + mv(scr("lid"), (0, 0, -70))),
    dict(no=6, title="FEET AND FOOT SCREWS", subtitle="AFTER THE LID SCREWS: THE FEET COVER THE CORNER LID SCREWS",
         base=SINK + [no("lid")], custom=mv(pick("heat-sink-foot"), (0, 0, -45)) + mv(scr("feet"), (0, 0, -95))),
]
for st in steps: st["balloon_base"] = []
rl = os.path.join(OUT, APN + ".REVLOG.md")
if os.path.exists(rl): os.remove(rl)
REV_ROWS = [("A", "Initial", datetime.date(2026, 11, 13)),
            ("B", "v2c: rebuilt from own sources (KiCad board STEPs, maker CAD); every part its own STEP with PN", None),
            ("C", "Maker CAD for the Sunon fan, Phoenix 3240083 ring lug and LTW bulkhead", None),
            ("D", "Separate feet, gap pads, heat-sink subassembly; fan wall 6.0; CnLinko USB-C bulkhead; standoffs on set-screw studs; 82 C tie mounts; ruthex maker STEP; install-order sheets", None)]
for L_, d_, dt in REV_ROWS: revs.add_release(rl, L_, d_, date=dt, title=APN)
spec = dict(items=items, title=f"ENCLOSURE ASSEMBLY {VAR}", pn=APN, project="custom-pdm enclosure v2c", revlog=rl, source="build_v2c.py (build123d)",
            open_hide=[no("lid"), no("heat-set-inserts-M4")] + [no(nm) for nm in scr("lid")], open_label="TRIMETRIC - LID REMOVED",
            iso_balloons={"open": []}, stage_sheets=[steps[:4], steps[4:]], bom_h=1.5,
            notes=["INSTALL ORDER: SHEETS 2-3 (STEPS 1-6). LID SCREWS BEFORE THE FEET.", "SET SCREWS (STUDS) 5.0 INTO THE M3 SINK BOSSES; F-F STANDOFFS SPUN DOWN ONTO THEM TO CLAMP THE BOARDS.",
                   "BOARDS DRAWN AS THE BARE PCB; COMPONENTS PER THE BOARD STEP.", "MODEL: build_v2c.py (build123d). THE STEP FILES GOVERN."],
            rev_marks=[dict(rev="D", bom=NO[pn]) for pn in NO if pn.startswith(("94868A", "92015A", "7566K", "RX-M4", "CPDM-ENC-110", "CPDM-ENC-112", "CPDM-ENC-113", "LP-16-", "CPDM-ENC-102", "CPDM-ENC-101", "ISO4762-M3x16", "ISO4762-M3x6"))])   # DRAWING-RULES 33: rev D triangles at the changed BOM rows
ck = asm.make_assembly(spec, os.path.join(OUT, APN + ".pdf"), os.path.join(OUT, APN + "_preview"))
res = json.load(open(os.path.join(OUT, APN + ".checks.json")))
print(json.dumps({k: res.get(k) for k in ("ok", "not_ballooned", "views")}, default=str)[:3000])
