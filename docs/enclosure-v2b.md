# Enclosure v2b (Grok TEST 2 b based, Fusion, real vendor models)

Status: build of 2026-11-12, branch `feat/enclosure-v2b`. Decisions behind it: `DECISIONS.md` 2026-11-12 (enclosure lines, h2a, v1-v5, A1a). Results, not decisions.
Scripts: `enclosure/v2b/src/` (build123d, WSL; `automation.yml` ids `enclosure-v2b-build`, `enclosure-v2b-render`). Vendor models: `enclosure/v2b/vendor/README.md`.
Fusion: project `custom-pdm`, folder `enclosure-v2b`, design `custom-pdm-enclosure-v2b-F1` (imported from the build STEP).

## 1. What it is

Grok's TEST 2 variant b, kept as close as the decisions allow: contoured MJF PA12 lid with a low terrace (power terminals) and a tall main body, slots on the main top, latch tabs and skirt, one-piece machined aluminium finned base, bolt-through feet, 12 x M4 screws from below into heat-set inserts in the lid.

Two base variants share everything above the base plate:
- **F1**: Grok's 2 x 30 mm Sunon MF30101V1 fans, now inside the heat-sink envelope (east fan bay, fins stop 18 mm short; fans bolt to a 3 mm wall machined in the sink and push west). Nothing sticks out past the enclosure outline.
- **F2**: one Noctua NF-A6x15 PWM blowing UP into the fins from a machined pocket in the fin field (centre x 150, y -52), 2 mm air gap under the fan inlet to the mounting surface, 24 swept fins + 24 splitters that turn the air outward in a radial spiral.

## 2. Changes vs Grok b, and why

| Change | Why (decision) |
|---|---|
| Housing deeper (lid y -132..12, main top z 66) | X1 / X2 on the front long side with real cut-outs, flange and panel-nut room (DECISIONS 2026-11-12 target look, h2a) |
| X1 TE HD34-24-21SN and X2 TE HDP24-24-47SE-L017 horizontal on the front wall in drafted turrets; real TE models, TE D-flat cut-outs | h2a, v4a |
| Feet: 24 AF hex bosses with two 4 mm webs each, bolt-through | "more reinforced-looking feet" |
| Copper fully inside; only terminal tops show through the terrace collars | v2 covered copper |
| Terminals = custom copper hex bosses, female-threaded (M6 for BATT / GND, M4 for OUT1-4); collars raised 6 mm (38.23 vs Grok 32.23) so the M6 boss is 15 mm tall: 6 mm stud thread below, 8 mm of the M6 x 10 lug screw above | v3b, A1a |
| BATT / GND copper bars (20 x 5 / 15 x 5) land on the board M6 feed terminals; OUT1-4 straps land on board B T1-T4 | e4a, b1b, p2a |
| Board A J3 and board B J6 bodies removed; flat taped wire ribbons from the pads to X1 / X2, tie points in the base | a1a, a2b, k1a |
| One sealed USB-C bulkhead (Amphenol LTW UC-00PMFY-SC7001) at z 30 on the front wall + Adafruit 5997 hub, one USB cable per board | y1a (replaces Grok's 3 USB slots) |
| Fans embedded in the sink (F1) or pocketed blowing up (F2) | v5 |
| Input boards kept on Grok's deck (25 mm M3 standoffs on board H holes) | v2: no clash with the real connector models |

## 3. Size and mass

| | F1 | F2 |
|---|---|---|
| Body (lid + base, no feet) | 280.2 x 144.0 x 104 mm | same |
| With feet (10 mm) | 280.2 x 144.0 x 114 mm | same |
| Front protrusion: X1 / X2 receptacles | 21 mm past the lid (y -153.2) | same |
| With mating plugs fitted | 61 mm past the lid (y -192.6) | same |

Mass: see section 6 (MASS_TABLE).

## 4. Heat (same Elmer model as `docs/heat-analysis.md`, HEAT_GEOM v2b-F1 / v2b-F2; 60 C air; board-top under the hottest chip; Tj = that + about 1-2 K)

HEAT_TABLE

Notes:
- Fans on: forced convection dominates, so the result holds flat or on a wall.
- Fans off: "open channels" (Elenbaas, fins as vertical channels open both ends) is the wall-mount case with the fins vertical; "fins down, closed top" (envelope method) is the flat case.
- F2 is an estimate, not CFD: fan curve against laminar friction in the radial channels at a representative radius (60 mm), turn / entry / exit losses K 2.5, half the flow bypassing at the open fin tips (all ASSUMED, `sim/heat/convection.py`), applied to a straight-fin field of the same wetted area as the swept fins. OpenFOAM was not run: Noctua's public CAD licence excludes flow simulation of their fan model, and a fan-curve CFD of the swirl is a separate job.
- Copper bar losses (about 2.2 W each at 150 A) are not in the model.

## 5. Clashes (interference check of every part pair, `enclosure/v2b/src/clearance_v2b.py`)

CLASH_TABLE

## 6. Parts (purchased parts from real models; see `enclosure/v2b/vendor/README.md` for sources and licences)

PARTS_TABLE

MASS_TABLE

## 7. Open items

- USB-C bulkhead, F1 Sunon fans and the TE panel nut are modelled from vendor drawings (no maker STEP reachable); check against real parts.
- Wire ribbons and USB cable routes are ASSUMED forms (flat taped ribbons, 4 mm cables); real harness bend radii to check at build.
- Panel-nut thickness ASSUMED 6 mm.
- CNC check of the base and the copper bosses (cnc-part-check) still to run on the final pick.
- Renders: `docs/diagrams/enclosure-v2b-*.png`.
