# Enclosure harness (inside the box): circuit list, pinouts, defaults

Scope (Dan 2026-11-20): every wire INSIDE the PDM box: X1 / X2 bulkheads to the board wire pads and lugs, input boards,
fans, USB bulkhead -> hub -> boards. Not in scope: the copper (BATT / GND bars and bosses, OUT1-4 risers) and the car
harness outside the box (X1 / X2 mating plugs, OUT1-4 10 AWG lugs).

Files (all in `harness/`). **The three CSV files are the master** (Dan 2026-11-21); everything else is generated from them:

| File | What | Made by |
|---|---|---|
| `enclosure-wire-list.csv` | **master**: one row per wire (harness-design skill column order) | by hand / agent |
| `enclosure-connectors.csv` | **master**: one row per connector / end (part numbers, kind, cavity labels, contact sizes) | by hand / agent |
| `enclosure-key.csv` | **master**: colour codes, wire families, label and length rules | by hand / agent |
| `enclosure.harness`, `enclosure.harnesslib` | harness.design v1.3 document and its parts library | `enclosure_harness.py build` |
| `enclosure-wiring-diagram.svg` (sheet 1), `-sheet2.svg`, `-sheet3.svg`, `.pdf` (all 3 sheets, 11 x 17 in) | wiring block diagram: blocks where the parts sit in the box, one line per group of wires with pins at both ends; sheets 2-3 = wire schedule | `enclosure_harness.py diagram` |

To change the wiring: edit the CSV, then `python harness/src/enclosure_harness.py build`, `... diagram`, `... check` (repo root, Python 3, standard library only).
- `check` proves: CSV rows <-> `.harness` conductors both ways; the built files are byte-for-byte what the CSVs give now; the `.harness` / `.harnesslib` keep the harness.design v1.3 top-level shape; every wire is exactly once in the drawn lines and once in the schedule; no text on text or on a line in the drawing; ampacity, contact range, seal range, splice fill.
- `src/enclosure_harness.py` holds the wire-part and contact data and the harness.design layout; `src/wiring_diagram.py` holds the drawing (block places and line lanes in its LAYOUT tables; a new connector pair in the CSV stops the build until it gets a place).
- `python harness/src/enclosure_harness.py xlsx` writes `enclosure-wire-list.generated.xlsx` (git-ignored Excel copy for people or for the harness.design Excel import; never read back). The old hand-kept `enclosure-wire-list.xlsx` is gone.
- Do not edit a generated file: the next build overwrites it and `check` fails until then.

Counts: 11 circuits, 111 wires (86 single, 8 twisted in 4 pairs, 17 USB cable cores), 32 connectors / ends (24 connectors, 4 ring lugs, 4 splices).

## 1. Circuit list

| # | Circuit | Source / protection | Controlled by | Return | Ends | Current per wire |
|---|---|---|---|---|---|---|
| C01 | A1 outputs 1-8 | board A1 BTS7008 channels (current limit = rating 7.5 A, w3a) | firmware | load ground outside the box | A1 J3 pads 3-10 -> X1 H-R | 7.5 A |
| C02 | A2 outputs 1, 3-8 | board A2, same | firmware | outside | A2 J3 pads -> X1 S, U-X, A, C | 7.5 A |
| C03 | B outputs 5-8 | board B BTS7004 (15 A) | firmware | outside | B T5-T8 ring lugs -> X1 B, D, E, G | 15 A |
| C04 | Board inputs IN1 / IN2 (A1, A2, B) | switch outside (to GND or 12 V) | - | SIG_GND | X2 7, 8, 15, 16, 23, 24 -> A J3 12 / 11, B J6 4 / 3 | < 0.01 A |
| C05 | Input-board inputs (A1 IN3-7, A2 IN3-7, B IN3-10) | switch outside | - | SIG_GND | X2 9-13, 17-21, 25-32 -> input board J2 1-5 / 1-8 | < 0.01 A |
| C06 | Analog inputs A1_AN, A2_AN, B_AN | sensor outside (0-5 V) | - | SIG_GND | X2 14, 22, 33 -> input board J2 9 | < 0.01 A |
| C07 | SIG_GND (switch / sensor returns only) | input board GND | - | board GND via the GH link | input board J2 10 (11 on #3) -> X2 35-38 | <= 0.1 A |
| C08 | CAN (Link ECU) | ECU | - | - | X2 2 / 3 -> splices SP1 / SP2 by X2 -> A1 J3 2 / 1, A2 J3 2 / 1, B J6 2 / 1 (twisted pairs) | < 0.1 A |
| C09 | Fans (2 x Sunon) | A2 OUT2 (fan output, 1 A limit, r7a) | firmware (temperature) | input board #2 J2 11 (GND) | A2 J3 7 -> SP3 -> fan + leads; fan - leads -> SP4 -> IN2 J2 11 | 2 x 64 mA max, 1 A limit |
| C10 | Input-board links (JST GH) | board +3.3 V / GND | - | - | A1 J6 / A2 J6 / B J7 <-> input board J1, pin n to pin n (A boards: 1-5, 9-12) | <= 0.2 A (GND on A2 carries the fan return) |
| C11 | USB service port | USB host outside | - | - | bulkhead rear USB-C -> cable U1 -> hub upstream USB-C; hub PORT1/2/3 pads -> pigtails U2/U3/U4 -> board B J2, A1 J5, A2 J5 | 0.5 A |

## 2. Pinouts (sources)

- **X1** HD34-24-21SN, **X2** HDP24-24-47SE-L017: cavity maps from `docs/box-connectors.md` (source of truth; TE drawing 0425-014-2400 rev H). X1 size 12 = B, D, E, G; spare F, T (plugged). X2 size 16 = 1, 4, 5, 6, 34 (spare, plugged); spare size 20 = 39-47 (plugged).
- **Board A J3 wire pads** (schematic netlist, `kicad-cli sch export netlist` of `hardware/board-a/DingoPDM.kicad_sch`, main c5d2370): 1 CAN_L, 2 CAN_H, 3 OUT8, 4 OUT7, 5 OUT6, 6 OUT5, 7 OUT2, 8 OUT1, 9 OUT4, 10 OUT3, 11 INPUT2, 12 INPUT1.
- **Board B J6 wire pads** (netlist of `hardware/board-b-max/dingoPDM-Max.kicad_sch`): 1 CAN_L, 2 CAN_H, 3 INPUT2, 4 INPUT1. **T1-T8** = PF_OUT1-8 (T5-T8 used here).
- **Input board J2** (Molex 43045-1200; netlist of `hardware/input-board/input-board.kicad_sch`): 1-8 INW_1-8, 9 AINW, 10-12 GND. **J1** (JST GH): 1-8 IN_1-8, 9 AIN, 10 +3V3, 11-12 GND.
- **Board A J6** (JST GH, netlist): 1-5 IN_3..IN_7, 6-8 not connected, 9 PF_IS2 (= analog input, PC2), 10 +3V3, 11-12 GND. **Board B J7**: 1-8 B_IN3..B_IN10, 9 B_AN, 10 +3V3, 11-12 GND.
- **Fan** Sunon MF30101V1-1000U-A99: 2 leads, UL1571 28 AWG, + red, - black, 145 +/- 10 mm, strip 5 +/- 0.3 (Sunon spec D03033580G-01 p. 6); 12 V, 55 mA rated / 64 mA max, -10 to +70 C (p. 3).
- **Hub** Adafruit 5997: upstream USB-C (or USBHOST pads), downstream PORT1-4 = pads 5V, D+, D-, GND, no downstream sockets (Adafruit learn guide "Adafruit CH334F Mini USB Hub Breakouts", pinouts page). Pad pitch / order on the board: TBD (not in the guide text).
- **Board USB-C**: GCT USB4085-GF-A (board A J5, board B J2; VBUS through diode D6, so no back-feed from the board).
- Layout positions and route lengths: `enclosure/v2c/src/build_v2c.py` rev D (branch chore/cad-models-fusion, read only) and its revD `meta.json` (hub box, T5-T8, USB X); board footprint positions from the `.kicad_pcb` files (A J6 at (-32.4, -1.5), B J7 at (38.294, 44.6), input board J1 (60, 24), J2 (10, 24)).

## 3. Defaults (this job, technical, with sources)

| Item | Default | Why / source |
|---|---|---|
| X1 wire type | SAE J1128 **GXL** 16 AWG (outputs), GXL 12 AWG (B OUT5-8) | X1 is an **N seal** insert: size 16 seals 2.54-3.40 mm, size 12 3.40-4.32 mm insulation OD (TE HD30/HDP20 catalog p. 83 "Recommended Wire Insulation O.D."). GXL 16 OD 2.70-2.90, GXL 12 3.50-3.80 (IEWC SAE J1128 sheet). TXL 16 (2.25-2.40) and M22759/16-16 (2.0) are too thin and would leak. |
| B OUT5-8 gauge | **12 AWG** (box-connectors.md says 14 AWG) | 15 A at 90 C box air in the 19-wire X1 bundle: 33 CFR 183.425 Table 5 (125 C insulation) x 0.61 (AWC ambient factor, 90 C) x 0.5 (7-24 conductors) = 14 AWG 12.2 A (fails), 12 AWG 15.2 A (passes). 12 AWG GXL also fits the size 12 N seal and contact 0462-210-1231 (12-14 AWG). heat-analysis.md already assumed 12 AWG. Needs Dan's yes to change box-connectors.md (SOT). Fallback if 14 AWG stays: SXL 14 (OD 3.45-3.80 fits the seal) but the ampacity check fails at 90 C. |
| 16 AWG outputs | 16 AWG GXL (as box-connectors.md) | 30 A x 0.61 x 0.5 = 9.2 A >= 7.5 A. |
| 20 AWG wire | **M22759/16-20** (ETFE, 150 C), Dan's library parts | OD 0.060 +/- 0.002 in = 1.47-1.57 mm (Glenair M22759/16 Table I): fits X2 E seal (1.02-2.41 mm, TE catalog p. 83) and the Micro-Fit 43030-0007 insulation limit (1.85 mm max, Molex data); TXL 20 (1.70-1.90) can exceed 1.85. Conductor 0.94-0.99 mm: tight in board B J6's 1.02 mm drill (check at build). |
| Contacts | X1 size 16 0462-201-1631, size 12 0462-210-1231 (both on hand, parts-audit 4.3); X2 size 20 0462-201-20141 (parts-audit C5); input board J2 Molex 43030-0007; GH SSHL-002T-P0.2 | Gauge ranges: TE common contact system manual p. 7, Molex 43030-0007 data (20-24 AWG), parts-audit (JST GH 26-30 AWG). `check` verifies every end. |
| Sealing plugs | X1 F, T and X2 1, 4, 5, 6, 34: 114017; X2 39-47: 0413-204-2005 | box-connectors.md "plug every unused cavity"; parts from parts-audit / Dan's library. |
| Strip lengths | size 20: 4.8, size 16: 7.1, size 12: 6.4 mm; board pads 4.0 mm; ring lug 8.0 mm; fan leads 5.0 (factory); Micro-Fit, GH, splices: TBD | TE common contact system manual p. 7 (20: 3.96-5.54, 16: 6.35-7.92, 12: 5.64-7.21; the extracted table was garbled: confirm on TE 0425-205-0000); pads ASSUMED 1.77 board + 1.5 protrusion + 0.75 gap; Phoenix 3240083 max strip 9 mm. |
| T5-T8 lugs | Phoenix 3240083 C-RC 6/M4 DIN (2.6-6 mm2, M4) | Same lug as OUT1-4 (one part); 12 AWG = 3.31 mm2 in range (phoenixcontact.com 3240083). Non-insulated: bare-metal clearance belongs to the enclosure lugcheck. |
| CAN topology | one splice per line by the X2 rear (SP1 CAN_H, SP2 CAN_L, TE Raychem D-436-37, 2 wires per side), twisted stubs to each board | A board pad hole takes one wire (1.77 / 1.02 mm drill), so a pad daisy chain is not possible; stubs are < 0.3 m (TP2 255 mm modelled). Termination stays on the board jumpers (DECISIONS 2026-11-08, C7b). |
| X2 35-38 (SIG_GND) mapping | input board #1 J2 10 -> 35, #2 J2 10 -> 36, #3 J2 10 -> 37, #3 J2 11 -> 38 | box-connectors.md says only "from input boards J2 pins 10-12". |
| Fan return | input board #2 J2 pin 11 (GND) via splice SP4 | A2 J3 has no GND pad; the GND copper is bolted under the bars. 0.13 A over the GH GND pair adds about 1 mV to the input ground. Alternative: ring lug under the A2 GND M6 screw (needs an enclosure screw-length check). |
| Fan feed | A2 J3 pad 7 -> SP3 -> both fan + leads (solder splices, Dan's generic solder splice part) | the factory leads (145 mm, UL1571 80 C PVC) cannot reach the board and should stay out of the hot air under the lid. |
| Colours | RD outputs / fan + / +3V3 / VBUS, WH inputs, VT analog, BK grounds, YE CAN_H, GN CAN_L, GY USB CC | Key sheet. |
| Labels | printed heat-shrink sleeve each end: `<wire ID> <signal> ><far end>` | Wires sheet From / To label. |
| Lengths | model route + 20 mm X1 / X2 fan-out + 2 x 15 mm service loop, up to 5 mm; TBD where the model has no route | first filled from the route polylines (`src/enclosure_harness.py` ROUTE); the CSV owns the values now. |
| Hub ports | PORT1 -> B, PORT2 -> A1, PORT3 -> A2, PORT4 spare | shortest runs. |

## 4. TBD (not guessed)

- Routes not in the model (lengths TBD, estimates in Notes): A1 / A2 inputs and CAN stubs to X2 / SP1-2, fan wires, the three JST GH links.
- **Fan pass-through**: the fans sit under the 8 mm plate in the fin bay; the model has no sealed way for their leads into the box (enclosure job).
- Part numbers: USB cable U1 (USB 2.0 C-to-C, 0.3 m), USB-C plug pigtails U2-U4 (VBUS, D+, D-, GND, 56 kohm Rp on CC), the 28 AWG >= 105 C GH wire, strip lengths for Micro-Fit / GH / splices, hub pad order.
- harness.design app check: the desktop app opened the file and did not rewrite it (2026-11-20); a visual check of the schematic and layout (dropped content shows only on screen) is still to do.
