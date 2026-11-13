# Enclosure v2b (Grok TEST 2 b based, Fusion, real vendor models)

Status: build of 2026-11-12, branch `feat/enclosure-v2b`. Decisions behind it: `DECISIONS.md` 2026-11-12 (enclosure lines, h2a, v1-v5, A1a; Dan's v2b review: b1a, b2a, b3a, b4a and the OUT1-4 wire-way) and Dan 2026-11-13 (c1b, d1a: OUT1-4 copper offset risers in a G10 carrier). Results, not decisions.
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
| Fans embedded in the sink (F1) or pocketed blowing up (F2) | v5; F1 goes forward (b2a), F2 kept as an alternative only |
| OUT1-4 wire-way: an open channel in the terrace from the OUT1-4 bay to the west lid edge (27.9 wide, floor z 19.2, 10.8 below the terrace top), between the BATT and GND collars; Grok's centre divider rib in the bay removed; bay floor 19.73 -> 19.2. The four ring lugs lie flat on the boss tops (z 20.73) and the 10 AWG wires leave horizontally at z 23.7 in four lanes (y -44.8 / -37.6 / -30.0 / -22.0); OUT1 / OUT3 lugs are turned 30 deg so their wires pass beside, not over, the OUT2 / OUT4 screws | Dan 2026-11-12: "the 4 terminals in the recess are too deep to connect a wire to; there needs to be a recess along the lid to the edge so there's a wire way" (t1a: lug flat, stud up) |
| Input boards kept on Grok's deck (25 mm M3 standoffs on board H holes) | v2: no clash with the real connector models |
| OUT1-4 (2026-11-13): the plain copper bosses on T1-T4 are replaced by 4 copper OFFSET RISERS held in ONE G10 carrier. Each riser = a 4 mm thick foot arm (R4) screwed to its REDCUBE terminal + a dia 8 seat column 8.1 mm away, so the lug seats are taller AND further apart. Two tiers: OUT2 / OUT4 (west pair) seats at z 19.0, OUT1 / OUT3 (east pair) at z 25.0, so the east pair's lugs and wires pass over the carrier between the west lugs. The carrier keys every riser (slots follow the riser outline, they can't turn), holds each lug in its own pocket with solid G10 walls between, and bolts to two M3 x 8 standoffs on board B H2 / H4, so lug-screw torque goes into the carrier and the heat-sink posts, not into the soldered REDCUBEs. The bay is now an open well over the carrier (its top is the bay floor); the wire-way still runs to the west lid edge, floor z 18.5. Grok-style thin ribs were not used (Dan: too thin / flexible). | c1b, d1a (Dan 2026-11-13) |

## 3. Size and mass

| | F1 | F2 |
|---|---|---|
| Body (lid + base, no feet) | 280.2 x 144.0 x 104 mm | same |
| With feet (10 mm) | 280.2 x 144.0 x 114 mm | same |
| Front protrusion: X1 / X2 receptacles | 21 mm past the lid (y -153.2) | same |
| With mating plugs fitted | 61 mm past the lid (y -192.6) | same |

Mass: see section 6.

## 4. Heat (unchanged by the wire-way: the lid is not in the heat model, the plate top inside the lid is adiabatic; same Elmer model as `docs/heat-analysis.md`, HEAT_GEOM v2b-F1 / v2b-F2; 60 C air; board-top under the hottest chip; Tj = that + about 1-2 K)

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
F1 rebuild with the OUT1-4 wire-way (2026-11-12, after Dan's review): still no unintended overlaps. New by-design overlaps: each 10 AWG wire end inside its ring-lug barrel (crimp), lugs touching their boss tops and screw heads. Closest new gaps: OUT1 wire to the wire-way wall 0.25 mm (flexible wire), OUT3 lug to the bay wall 0.65 mm, wires to the OUT2 / OUT4 screws 2.0 mm, wires to the bosses 2.4 mm. Fixed on the way: OUT3 and OUT1 wires against the wire-way walls (lanes re-spaced).
F1 rebuild after e1a (2026-11-13): no unintended overlaps; on the way the widened carrier hit the BATT / GND bars (carrier now stops at y -53.4 / -13.14, just clear of them), the lower lug tips hit the wire-way wall (lower lugs turned to 172 / 188 deg) and the well liner touched the BATT boss (re-cleared dia 16). Earlier F1 rebuild with the OUT1-4 copper risers + G10 carrier (2026-11-13, c1b / d1a): no unintended overlaps. New by-design overlaps: M4 x 6 foot screws in the REDCUBE threads, M4 x 8 lug screws in the copper seats, M3 standoffs in board B H2 / H4 and the sink posts, wire ends crimped in the lug barrels. Closest new gaps: carrier to BATT / GND bars 0.46 mm (bars notched dia 11 at the standoffs), lid to lugs 0.5 mm, carrier to lid 0.6 mm, carrier to foot screws 0.6 mm, carrier to J6 bundle 1.03 mm, lid to wires 1.4 mm, risers to J6 bundle 1.5 mm, carrier to wires 1.9 mm, lugs to foot screws 2.27 mm. Fixed on the way: risers OUT2 / OUT4 touching (R5.5 obrounds at the 9.5 mm T pitch; now foot arm R4 + column, 1.5 mm apart with a G10 web), upper lug barrels 0.39 mm apart (now 2.1 mm), carrier against the wire-way liner and the well, J6 ribbon through the risers (rerouted between the tiers).
Both Fusion designs (`custom-pdm-enclosure-v2b-F1` v4, `-F2` v3, saved 2026-11-13 14:00 ET) hold the e1a builds (F1 risers + carrier with the e1a clearance fix; F2 smooth fins + flow cone + the same OUT stack), imported from WSL `~/scratch/encl-v2b/runs/<variant>/custom-pdm-enclosure-v2b-<variant>-assembly.step`.

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
| OUT1-4 ring lugs | Phoenix Contact 3240083 (M4, 10-14 AWG, non-insulated; M4 kept: the lug screw goes into copper, not into the REDCUBE) | modelled from catalogue dims 8.0 x 17.5 x 0.99 (Digi-Key / TraceParts model page would not load; barrel OD 6 ASSUMED) |
| OUT1-4 wires | 10 AWG GXL (31 A each) | OD 4.2 ASSUMED |
| Copper bosses BATT / GND (custom, 3-axis mill) | hex AF 13 x 15, M6 female both ends, C110 copper | this build |
| Copper offset risers OUT1-4 (custom, 3-axis mill) | C110; foot arm R4 x 4 thick with M4 clearance hole on the T centre, seat column dia 8, seat 8.1 mm from the T centre, M4 tapped 10 deep; height 10.27 (OUT2 / OUT4) and 16.27 (OUT1 / OUT3); from 12 x 20 flat bar (low) and 20 x 20 square bar (high), 2 setups (top profile + holes, flip and face to height); no undercuts | this build |
| Carrier OUT1-4 (custom, 3-axis mill) | G10 / FR4 (stiffer than PEEK so it does not creep under bolt load at 70-80 C, cheap, good insulator; PEEK would be tougher and cleaner to cut but softer and dearer); about 50.5 x 55.2 x 16.2 mm (with ears) from 3/4 in plate; all features from the top (riser key slots through, lug pockets 5 deep, ears 5 thick, M3 counterbores), flip and face; carbide tools + dust extraction for glass-epoxy | this build |
| Carrier standoffs | 2 x M3 x 8 M-F hex AF 5.5 on board B H2 / H4 (replace those board screws; male end into the sink posts) + 2 x M3 x 8 SHCS | PN TBD |
| Riser screws | foot: 4 x M4 x 6 ISO 4762 into the REDCUBE (2.0 of its 2.5 mm thread), max 1.2 N*m, threadlocker; lug: 4 x M4 x 8 ISO 4762 into the copper seat (7 mm engagement) | build123d fasteners |
| Copper bars (custom) | BATT 20 x 5, GND 15 x 5, C110, insulating film under | this build |
| Base (custom, one-piece 6061) | F1 / F2 | this build |
| Lid, input deck (MJF PA12) | | this build |

Mass of the made parts (densities Al 2.70, PA12 1.01, Cu 8.94 g/cm3; boards, connectors, fans and screws not included):

| Part | F1 | F2 |
|---|---|---|
| Base / heat sink (6061) | 1774 g | 1544 g |
| Lid (PA12) | 233 g | 233 g |
| Input deck (PA12) | 25 g | 25 g |
| BATT + GND bars (Cu) | 295 g | 295 g |
| Copper bosses BATT / GND (Cu) | 34 g | 34 g |
| OUT1-4 risers (Cu) | 28 g | 28 g |
| OUT1-4 carrier (G10, 1.85 g/cm3) | 24 g | 24 g |
| Flow cone (PA12) | - | 3 g |
| Total | 2413 g | 2187 g |

(2026-11-13 builds, `enclosure/v2b/src/mass_v2b.py`.)

## 5b. OUT1-4 risers + carrier (2026-11-13, Dan c1b / d1a / e1a)

- e1a (Dan 2026-11-13, after reviewing the riser / carrier render): the first riser layout had the upper (east) lug ring 0.9 mm from a lower lug and 1.0 mm from a lower lug-screw head. Fix applied: upper lug tier raised 4 mm (seat z 25 -> 29, lug top about flush with the terrace top z 30), seats moved to OUT2 / OUT4 (28.9, -44.9 / -21.64) and OUT1 / OUT3 (43.5, -43.2 / -23.34) (mirrored about y -33.27), lug angles OUT2 172, OUT4 188, OUT1 166, OUT3 194 deg, wire lanes y -43.3 / -37.8 / -28.7 / -23.2, G10 carrier widened to y -53.4 to -13.14 (just clear of the BATT / GND bars), upper block y -51.9 to -14.64. The wire-way between the BATT and GND collars is unchanged.
- Bare-metal clearances after e1a (`enclosure/v2b/src/lugcheck_v2b.py`, F1 build, 3-D min distance): lug to lug min 5.57 mm (OUT1-OUT3); lug to any other-net screw min 5.24 mm (upper lug over the lower lug-screw head); lug to other risers min 6.70 mm. Same-net pairs (a lug and its own riser foot screw) are not counted. G10 carrier walls (from the build geometry): lower-pocket to carrier edge 3.0 mm, upper-pocket to edge 3.2 mm, lower-to-upper pocket wall 3.7 mm (no line of sight between lugs).
- Wires: insulated wire may touch plastic (Dan 2026-11-13); only bare metal (lugs, screws, risers) is held to real clearance, so no wire-to-wall gap is required.

- REDCUBE 74650074R (board B T1-T4): M4 internal thread, max tightening torque 1.2 N*m and 50 A max at 20 C (Wurth datasheet 74650074R, properties table, https://www.we-online.com/catalog/datasheet/74650074R.pdf); thread length 2.5 mm per the Wurth product page (not legible in the datasheet text; check on the drawing); body 3.0 mm tall (KiCad / Wurth 3D model). The foot screw (M4 x 6) is tightened to that limit once; afterwards every lug torque goes into the copper seat and the G10 carrier, which is keyed on the risers and bolted to the heat-sink posts through two M3 standoffs.
- Lug seats (after e1a): OUT2 / OUT4 at z 19.0 (west pair), OUT1 / OUT3 at z 29.0 (east pair); lugs flat on the seat columns, wires leave horizontally (t1a) in four lanes y -43.3 / -37.8 / -28.7 / -23.2 (low / high / high / low tier, z 22 / 32 / 32 / 22).
- Separation: west pair lugs sit in separate G10 pockets with solid G10 between them (no line of sight); east pair rings are separated by a solid G10 wall >= 4.9 mm in the raised carrier block, their barrels end 2 mm apart in air; east lugs pass 5.2 mm above the west lug-screw heads (was 1.0 before e1a). Riser feet of neighbouring terminals (T1-T4 pitch 9.5 mm) are 1.5 mm apart with a G10 web between.
- Tool access: every M4 lug screw has an open dia 11 pocket above it (3 mm hex key / bit); west screw heads top z 24 (6 below the terrace), east heads top z 34 (4 above the terrace). The foot screws are reached through the open key slots before the lugs go on.
- Assembly: 1) risers onto T1-T4 (M4 x 6, 1.2 N*m max, threadlocker); 2) standoffs into the sink posts through board B H2 / H4; 3) carrier down over the risers, 2 x M3 x 8 into the standoffs; 4) lugs + M4 x 8.
- Copper bars: notched dia 11 (insulating sleeve) where the carrier standoffs pass at board B H2 / H4: BATT 20 x 5 keeps about 13 x 5 there, GND 15 x 5 keeps about 8.7 x 5 (about 3.5 A/mm2 at 150 A over a few mm).
- Clashes (F1 rebuild): see section 5; renders `enclosure-v2b-F1-outbay-sw.png`, `-outbay-nw.png`, `-outstack-exploded.png`, `-section-OUT-bay.png`, `-iso.png`, `-iso-nw.png`, `-iso-lid-off.png`, `-top.png`, `-section-BATT-stud.png` re-rendered 2026-11-13.

## 5c. F2 update (2026-11-13, Dan: smooth fins + flow cone; F1 stays the pick, b2a)

- Swept fins rebuilt as SMOOTH solids: each fin centreline is one tangent-continuous spline through the log spiral (points every 2 mm, theta = theta0 + 0.55 ln(r / 31)), offset +/- 1.25 to a constant 2.5 mm thickness with round (arc) ends, extruded to the 30 mm fin depth, fin tips filleted 1.0; no polyline facets, so the 3-axis toolpath follows one smooth curve per side. 24 long fins from r 31 + 24 splitters from r 62.
- Narrowest channel 4.61 mm (normal pitch r x 2 pi / N x cos 28.8 deg minus the 2.5 mm fin, at r 31 for the long fins and r 62 where the splitters start; channels widen outward). Tool: dia 4 mm 3-flute carbide end mill for aluminium with 0.5 corner radius (0.3 mm per side to the channel walls, 0.5 mm root radius at the plate), long-reach for the 30 mm fin depth, with step-downs; fin root fillets come from that corner radius. Fin ends are R 1.25 (convex), no concave corner tighter than the tool.
- Flow cone (replaced 2026-11-13 16:05, Dan's sketch: "the reverse shape of a velocity stack"): MJF PA12, revolved CONCAVE trumpet flare. Generator = quarter-ellipse centred at (r 29, z_apex): r = 29 - 28 cos(phi), z = z_apex + 10.5 sin(phi), phi 0..90 deg. It starts as a narrow point (tip R 1.0, rounded) aimed down at the Noctua hub with a vertical tangent, 1.5 mm above the fan outlet face (z_apex -18.5; the hub is solid, no flow there), and flares outward to base R 29 on the plate underside (z -8) with a HORIZONTAL tangent, so it blends tangentially into the plate and the axial flow turns smoothly 90 deg into the radial channels. R 29 is about the NF-A6x15 blade-tip circle and ends 2 mm inside the fin roots (r 31), so no fin is trimmed and no channel is blocked; the fan posts (r 35.4, dia 8) clear it by 2.4 mm. Height 10.5, volume 2.86 cm3, about 3 g. Mount: the pointed tip leaves no room for a screw head, so one M3 x 12 countersunk screw (ISO 10642) goes in from the plate TOP (90 deg countersink, head flush) into an M3 heat-set insert (short, 4 long, bore dia 4.0 x 4.3 deep) in the cone base; the insert wall is >= 4 mm. The old paraboloid (convex dome, R 26) and its M3 tap from below are gone.
- Fan inlet: the Noctua inlet face is at z -36, the mounting surface (foot bottoms) at z -48, so 12 mm free inlet gap under the fan.
- Heat: F2 numbers in section 4 are from the straight-fin-equivalent estimate and do not include the cone (old or new); the cone change does not alter that estimate method, so they were not re-run (an F2 flow simulation is still excluded by Noctua's CAD licence).
- Renders: `enclosure-v2b-F2-iso.png`, `-under.png`, `-section-fan-cone-fins.png`, `-cone-iso.png` (re-rendered 2026-11-13 after the cone change). The cone change was applied to the existing F2 build with `enclosure/v2b/src/cone_patch_v2b.py` (the full build needs the git-ignored PACK / VENDOR folders); `build_v2b.py` carries the same geometry for the next full build.

## 7. Open items

- Dan's v2b review (2026-11-12): b1a connectors sticking out 21 mm (61 mm with plugs) are fine; b2a F1 goes forward (F2 files kept, no more work); b3a gap pad k >= 3 W/mK; b4a no OUT1-4 straps (bosses straight on T1-T4).
- OUT1-4: superseded 2026-11-13 by the copper offset risers + G10 carrier (section 5b), clearances fixed by e1a (lug-to-lug >= 5.5 mm, lug-to-other-screw >= 5.2 mm, carrier walls >= 3.0 mm).
- BATT / GND collars: boss top z 39.23, 9.2 above the terrace, so their M6 lugs lie flat and the wires leave horizontally clear of the lid; open tool access from above; route those wires west, north or south (the main body starts about 40 mm east).

- USB-C bulkhead, F1 Sunon fans and the TE panel nut are modelled from vendor drawings (no maker STEP reachable); check against real parts.
- Wire ribbons and USB cable routes are ASSUMED forms (flat taped ribbons, 4 mm cables); real harness bend radii to check at build.
- Panel-nut thickness ASSUMED 6 mm.
- CNC check of the base and the copper bosses (cnc-part-check) still to run on the final pick.
- Wire-way renders (2026-11-12): `enclosure-v2b-F1-outbay-sw.png`, `-outbay-nw.png`, `-iso.png`, `-iso-nw.png`, `-top.png`, `-section-OUT-bay.png`, `-section-BATT-stud.png` re-rendered; the other F1 views are from the build before the wire-way.
- Renders: `docs/diagrams/enclosure-v2b-*.png` (F1 full set incl. sections through the BATT stud, the OUT bay and the board / sink stack; F2 iso, iso NW, lid off, underside, stack section). F2 renders are from the build before the 1 mm fan-post fix (not visible at render scale).
- A1a (raised collars) recorded here: the M6 boss is 15 mm tall, 6 mm of the board stud thread below and 8 mm of the M6 x 10 lug screw above, with a 1 mm gap between.
