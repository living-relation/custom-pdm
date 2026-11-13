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
| BATT / GND copper bars (20 x 5 / 15 x 5, C110) run B -> A1 -> A2 and land on every board's M6 feed terminals; OUT1-4 copper bosses sit straight on board B T1-T4 (tops in Grok's recessed terrace bay), so no straps are needed (p2a's straps fall away: the boss IS the covered terminal) | e4a, b1b, v2 / v3b |
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

Mass: see section 6.

## 4. Heat (same Elmer model as `docs/heat-analysis.md`, HEAT_GEOM v2b-F1 / v2b-F2; 60 C air; board-top under the hottest chip; Tj = that + about 1-2 K)

Values: heat-sink max / board top under the hottest chip for gap-pad k = 1 / 3 / 6 W/mK (C). Tj limit 150 C.

| Variant | Air case | Worst load 31.1 W | Typical 17.4 W |
|---|---|---|---|
| F1 | fans on (flat or wall) | 74.5 / 142 / 119 / 113 - pass (k 1: about 6 K margin) | 68.1 / 106 / 94 / 90 - pass |
| F1 | fans off, wall (fins vertical, open channels) | 90.6 / 159 / 139 / 133 - k 1 fails, k 3 passes | 81.7 / 121 / 109 / 106 - pass |
| F1 | fans off, flat (fins down) | 133.8 / 202 / 182 / 176 - fail | 105.8 / 145 / 133 / 130 - pass (k 1 thin) |
| F2 | fan on (flat or wall), ESTIMATE | 78.0 / 146 / 122 / 116 - pass (k 1: about 2 K margin) | 70.1 / 108 / 95 / 92 - pass |
| F2 | fan off, wall | 103.9 / 172 / 148 / 142 - k 1 fails, k 3 marginal | 90.1 / 128 / 115 / 112 - pass |
| F2 | fan off, flat | 137.5 / 205 / 181 / 175 - fail | 107.9 / 146 / 133 / 129 - pass (k 1 thin) |

Reading it: with the fans running both variants keep every chip under 150 C at worst load (pick a gap pad of k 3 or better); F1 runs about 3-4 K cooler than F2 and is a full simulation input, F2 is an estimate. With the fans off, worst-case load needs the firmware thermal limit (e3c) in both. Fans see 60 C intake air in both (they push), inside the Sunon 70 C rating; Noctua's rating is to check. Plots: `docs/diagrams/heat-v2b-F1-*.png`, `docs/diagrams/heat-v2b-F2-*.png`.

Notes:
- Fans on: forced convection dominates, so the result holds flat or on a wall.
- Fans off: "open channels" (Elenbaas, fins as vertical channels open both ends) is the wall-mount case with the fins vertical; "fins down, closed top" (envelope method) is the flat case.
- F2 is an estimate, not CFD: fan curve against laminar friction in the radial channels at a representative radius (60 mm), turn / entry / exit losses K 2.5, half the flow bypassing at the open fin tips (all ASSUMED, `sim/heat/convection.py`), applied to a straight-fin field of the same wetted area as the swept fins. OpenFOAM was not run: Noctua's public CAD licence excludes flow simulation of their fan model, and a fan-curve CFD of the swirl is a separate job.
- Copper bar losses (about 2.2 W each at 150 A) are not in the model.

## 5. Clashes (interference check of every part pair, `enclosure/v2b/src/clearance_v2b.py`)

F1 (final build): no unintended overlaps. Every remaining overlap is by design: screws and studs in their threads (copper bosses, M6 / M4 terminals on the boards, M3 into the sink and standoffs), the mating plugs seated in X1 / X2, wire ribbons soldered on the board pads, and USB cable ends entering the bulkhead, the hub and the three board USB-C receptacles (cable plugs are not modelled).
Fixed in this build: F1 fan against a foot web (fans moved to mid +/-16 mm), USB-C cable through board A2 and through the terrace (bulkhead raised to z 30, cable lane at z 30 under the main lid and z 22 under the low terrace), USB cables against the B J6 ribbon (board lane at z 7.8), A2 ribbon against X2's rear body (routed 1 mm clear), B J6 ribbon against X2.
F2 (final build): same result, no unintended overlaps. Fixed: the Noctua fan sat 1 mm into its four mounting posts (the public model is 16 mm tall, not 15); pocket and posts now sized to the model.
Both Fusion designs (`custom-pdm-enclosure-v2b-F1`, `-F2`) hold these final builds.

## 6. Parts (purchased parts from real models; see `enclosure/v2b/vendor/README.md` for sources and licences)

| Part | Part number | Model source |
|---|---|---|
| X1 receptacle (outputs) | TE HD34-24-21SN | TE customer view model (te.com, terms accepted, v4a) |
| X1 mating plug | TE HD36-24-21PN | TE customer view model |
| X2 receptacle (signals, CAN) | TE HDP24-24-47SE-L017 | TE customer view model |
| X2 mating plug | TE HDP26-24-47PE-L015 | TE customer view model |
| Panel nuts X1 / X2 | TE 2411-001-2405 | modelled from TE spec 0425-021-0000 (AF 47.6; thickness ASSUMED 6) |
| USB-C bulkhead | Amphenol LTW UC-00PMFY-SC7001 | modelled from the UC series catalogue (no maker STEP reachable) |
| USB hub | Adafruit 5997 (CH334F, 4 port) | Adafruit_CAD_Parts STEP (MIT) |
| Fans F1 | 2 x Sunon MF30101V1-1000U-A99 (30 x 30 x 10) | modelled from Sunon spec D03033580G-01 (no STEP published) |
| Fan F2 | Noctua NF-A6x15 PWM (60 x 60 x 15) | Noctua public CAD STEP |
| Boards A1, A2, B, input boards | this repo | board STEPs (J3 DT15 / J6 Micro-Fit bodies removed, a1a / a2b) |
| Heat-set inserts | M4 | modelled to standard dims |
| Screws | ISO 4762 / threaded rod | build123d fasteners (screw_dimensions.csv) |
| Copper bosses (custom, 3-axis mill) | M6: hex AF 13 x 15, M6 female both ends; M4: round 9.5 with 8 mm wrench flats, M4 female; C110 copper | this build |
| Copper bars (custom) | BATT 20 x 5, GND 15 x 5, C110, insulating film under | this build |
| Base (custom, one-piece 6061) | F1 / F2 | this build |
| Lid, input deck (MJF PA12) | | this build |

Mass of the made parts (densities Al 2.70, PA12 1.01, Cu 8.94 g/cm3; boards, connectors, fans and screws not included):

| Part | F1 | F2 |
|---|---|---|
| Base / heat sink (6061) | 1774 g | 1540 g |
| Lid (PA12) | 240 g | 240 g |
| Input deck (PA12) | 25 g | 25 g |
| BATT + GND bars (Cu) | 300 g | 300 g |
| Copper bosses | 59 g | 59 g |
| Total | 2398 g | 2163 g |

## 7. Open items

- USB-C bulkhead, F1 Sunon fans and the TE panel nut are modelled from vendor drawings (no maker STEP reachable); check against real parts.
- Wire ribbons and USB cable routes are ASSUMED forms (flat taped ribbons, 4 mm cables); real harness bend radii to check at build.
- Panel-nut thickness ASSUMED 6 mm.
- CNC check of the base and the copper bosses (cnc-part-check) still to run on the final pick.
- Renders: `docs/diagrams/enclosure-v2b-*.png` (F1 full set incl. sections through the BATT stud, the OUT bay and the board / sink stack; F2 iso, iso NW, lid off, underside, stack section). F2 renders are from the build before the 1 mm fan-post fix (not visible at render scale).
- A1a (raised collars) recorded here: the M6 boss is 15 mm tall, 6 mm of the board stud thread below and 8 mm of the M6 x 10 lug screw above, with a 1 mm gap between.
