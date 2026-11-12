# Enclosure 3D v1 (low profile) - design note

Status: v1 draft for Dan to review, 2026-11-12, branch `feat/enclosure-lowpro`. Built from `DECISIONS.md` (2026-11-11 / 2026-11-12). Model, scripts and re-run: `enclosure/lowpro/README.md`. Heat: `docs/heat-analysis.md` section 6.
Naming (DECISIONS 2026-11-12): top / bottom = board surfaces; front edge = PCB -Y (faces the front wall), back edge = PCB +Y, left / right end = PCB -X / +X. Enclosure: front wall = X1 / X2 / USB-C side, left end = BATT / GND studs, right end = OUT1-4 studs.
Marks: **ASSUMED** = my choice, **TBD** = not confirmed by a primary source.

## 1. Size and weight
| Item | Value |
|---|---|
| Body (base incl. both stud ledges x width x height) | **346.2 x 150.3 x 104.5 mm** (94.5 without the 10 mm feet). Limit (e1) about 356 x 152 x 127 |
| Lid (PA12) | 278.2 x 150.3 x 60 mm, wall / top 3 mm; base plate below it, stud ledges 34 mm at each end |
| Sticking out past the front wall | X1 about 14 mm, X2 about 26 mm (TE drawing), USB-C about 10 mm, plus the mating plugs (X1 harness side adds 38.6 mm, TE catalog) |
| Weight, enclosure parts | base 2.17 kg, duct cover 0.20, lid 0.26, BATT + GND bars 0.25, OUT straps 0.05, stud blocks 0.05 = **about 3.0 kg** (densities: Al 2.70, PA12 MJF 1.01, Cu 8.93, G10 1.85 g/cm3). Not included: boards, connectors, studs, screws, fan |

What sets the height: X1 / X2 flange 50.8 mm on the front wall -> lid 60 mm; base plate 8 + fins 25 + duct cover 1.5 + feet 10 (fan intake gap) below.

## 2. Layout (target layout, DECISIONS 2026-11-12)
- Boards A1, A2, B in a row, 2 mm apart, turned 180 degrees so their front edge faces the front wall. Board row 0 .. 260.2 mm.
- Clearances inside the lid (ASSUMED): left / right 6 mm, back 14 mm (right-angle USB-C plugs on the boards' back edge), front 35 mm (X1 / X2 bodies behind the wall clear the GND bar by about 3 mm).
- Base = heat sink: one machined 6061-T6 (or 6063) part. Plate 8 mm, pedestals 3 mm + 1 mm gap pad under every driver chip (bottom surface), M3 bosses at every board hole (e7b: corner screws only), 26 fins down (2 mm @ 6 mm, 25 mm deep) along X, stud ledges 34 mm at both ends, 4 feet with M6 clearance.
- Fan (e3c): **one Noctua NF-A6x15 FLX** (60 x 60 x 15, 12 V, 19.8 dB(A), 13.77 CFM, 2.43 mm H2O, -10 to +70 C, [noctua.at spec](https://www.noctua.at/en/products/nf-a6x15-flx/specifications)). It sits in a 75 mm plenum under the left end and pushes 60 C cabin air along the fins to the open right end. A 1.5 mm aluminium cover on the fin tips turns the channels into ducts (all fan air through the fins). Feet give the 10 mm intake gap. Switching on a software-set temperature limit is a firmware item (e3c).
- Lid (e2a): MJF PA12. 11 M4 x 12 screws hold it down: each sits at the bottom of a lid boss, driven through an 8 mm access hole from the top (caps TBD), into a tapped hole in the base plate. Heat-set inserts (M3) only where the input boards mount to the lid.
- Front wall (j1a, y1a): X1 over A2, X2 and the USB-C bulkhead in front of B, all horizontal.
- Input boards (x2c, x2a): one under the lid ceiling over each main board, parts facing down, on 4 mm bosses; JST GH cables to A J6 / B J7 (x1a). Lifting the lid lifts them with it, so every board screw and terminal is reachable. Their parts sit at Z 47-53, over the bars (top of the bar screws about Z 29).
- USB (y1a): Adafruit 5997 CH334F mini 4-port hub (31.6 x 20.4 x 4.8, [product page](https://core-electronics.com.au/adafruit-ch334f-mini-4-port-usb-hub-breakout.html.plain.md)) on 4 mm standoffs behind the bulkhead; one cable to each board's USB-C (back edge). Back-feed check: each board's VBUS pin goes only to a Schottky anode (A: D15, B: D6, cathode +5V) and a sense divider (A: R56 / R57, B: R4 / R5), so the boards cannot drive VBUS. Note: with 12 V off, the laptop's USB then powers the three boards' +5V rails through those diodes (bus power budget TBD).
- Wiring: board A pads (old J3 holes, board centre) and board B pads (old J6 holes, centre, wires flat under the T1-T4 straps, REDCUBE 3.0 mm tall) run to X1 / X2; a slotted cable-tie post on the base in front of each board A (k1a); board B T5-T8 screw terminals wired to X1 (v2b). Wires are not modelled.

## 3. Power copper (e4a, b1b, p2a)
| Part | Size | Current check (hand calc, Cu 2.19e-8 Ohm m at 90 C) |
|---|---|---|
| BATT bar, GND bar | Cu-ETP 20 x 3 mm (60 mm2), 273 mm stud -> B terminal, on top of the three boards' M6 terminals (Wuerth 7461084, 160 A) | at 150 A the whole length: 0.10 mOhm, 15 mV, **2.2 W per bar** (worst case; bar heat is NOT in the heat model). 2.5 A/mm2. Rule-of-thumb busbar tables put 20 x 3 Cu near 200 A for about 30 K rise in free air (to verify for the enclosed case) |
| OUT1-4 straps | middle pair 8 x 2 (16 mm2), outer pair 5 x 3 (15 mm2), on the REDCUBE M4 tops (Z 8.7) | 31 A: about 2 A/mm2, about 0.1 W each |
| BATT / GND studs | M8, left ledge, on 22 mm G10 blocks (insulated from the Al base) | Blue Sea 2202 / 2201 (C5); real stud geometry and rating TBD |
| OUT1-4 studs | M6, right ledge, on 16 mm G10 blocks | part TBD |
- Studs point up, ring lug flat (t1a). Bars pass the left lid wall, straps the right lid wall, in slots (gasket or potting TBD).
- Gaps (ASSUMED, check against the insulation rule you want): bar bottom to base 19.2 mm; strap top to bar bottom 7.5 mm; straps 8.7 mm above the Al ledge.
- Copper paths are routed so no stud sits under a bar and no strap crosses a terminal (checked in the model).

## 4. Checks run
- Interference (`enclosure/lowpro/src/check_lowpro.py`): every part pair, solid by solid: **0 unexpected overlaps**; the only overlaps are by design (studs threaded into their blocks). Result: `enclosure/lowpro/step/check.json`.
- Heat: `docs/heat-analysis.md` section 6.

## 5. BOM additions (for the enclosure)
| Item | Qty | Part | Status |
|---|---|---|---|
| Fan | 1 | Noctua NF-A6x15 FLX | picked |
| USB hub | 1 | Adafruit 5997 (CH334F, 4 port) | picked; temperature rating not stated (TBD) |
| USB-C bulkhead, IP67, jam nut | 1 | Amphenol LTW UC / USC panel series (e.g. USC-00PMFY-SC7001) | PN and cut-out TBD (DigiKey page not readable) |
| Right-angle USB-C cables | 3 | short, to the hub pads | TBD |
| Cu bars 20 x 3 | 2 | Cu-ETP, cut and drilled | ASSUMED |
| Cu straps | 4 | 8 x 2 (2), 5 x 3 (2) | ASSUMED |
| Studs + G10 blocks | 2 + 4 | Blue Sea 2202 / 2201 (BATT / GND), M6 studs (OUT) | TBD |
| Gap pad | 1 sheet | k >= 3 W/mK, 1 mm, insulating | TBD |
| Lid screws | 11 | SHCS M4 x 12 (through 8 mm access holes) + caps | ASSUMED |
| Feet / mounting | 4 | M6 | ASSUMED |

## 6. Open questions for Dan
- **i1. X2 and the plugs stick out past the front wall** (X2 about 26 mm, X1 about 14 mm, plus the mating plugs; body is 150.3 mm wide, limit about 152). a) Fine, the size limit is for the body (recommended); b) recess X1 / X2 in pockets in the lid front (the box gets about 25 mm deeper inside).
- **i2. Fan off, the box cannot shed worst-case heat** (heat-analysis section 6: sink 125 C flat, 142 C on a wall). a) Keep the ducted fan; the fan switches on below the danger point and firmware derates outputs if it gets hot or the fan fails (recommended: low, quiet, coolest with the fan); b) drop the duct cover (open fins: better with the fan off, the fan then needs a shroud and cools less); c) taller fins (more height).
- **i3. Wall mounting orientation.** a) Long axis vertical, fan end down (recommended: air rises along the ducts); b) long axis horizontal.
- **i4. Stud split.** a) BATT / GND on the left ledge, OUT1-4 on the right ledge (as modelled; recommended: shortest copper, no crossings); b) all six studs at one end (longer bars, straps cross under the bars).

## 7. Not done
Wires, harness and cable lengths; gaskets and slot seals; lid styling beyond rounded edges; real stud, bulkhead and connector cut-out drawings; drawings for manufacture (`cad-drawing` skill) and the CNC check (`cnc-part-check`) once v1 is approved.
