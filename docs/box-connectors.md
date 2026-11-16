# Box connectors (enclosure wall)

Decisions: Dan, 2026-11-09 (see DECISIONS.md). TE Deutsch HD30 / HDP20 parts, mostly on hand.
Cavity IDs come from TE customer drawing 0425-014-2400 rev H ("Arrangement of contact location for HDP20 and HD30
series connectors, shell size 24"). That drawing shows the rear (wire/grommet) end. Cavity IDs are the same on both
halves, so a wire's ID matches from box to harness.

Contact ratings (TE Deutsch common contact system, max at 125 C continuous): size 20 = 7.5 A (16-20 AWG),
size 16 = 13 A (14-20 AWG), size 12 = 25 A (12-14 AWG), size 8 = 60 A (8-10 AWG), size 4 = 100 A (6 AWG).

Rule (Dan, standing): anything that sources power has **socket** contacts on the box side, so no live pins are exposed when the connector is unplugged.

Inside the box, wires solder straight to the boards (Dan 2026-11-12, e6a / a1a / a2b): board A J3 = wire pads in the old
DT15-12PA holes (1.77 mm drill: 16 AWG outputs, 20 AWG IN / CAN), silkscreen CL CH O1-O8 I1 I2 between the pad rows;
board B J6 = wire pads in the old Micro-Fit 2x2 holes (1.02 mm drill, 20 AWG), silkscreen CL CH I1 I2. Footprints:
`tools/wirepads.py`. "J3 pad 8" below = the J3 hole numbered 8. Board B J6 wires run flat on the top surface under the
OUT1-4 copper risers on T1-T4 (REDCUBE 74650074R body is 3.0 mm tall; layout in `docs/enclosure-v2b.md` section 5b).

## Overview

| # | Box side (panel) | Harness side | Insert | Carries |
|---|---|---|---|---|
| X1 | HD34-24-21SN (aluminum, flange, sockets) | HD36-24-21PN (pins) | 24-21: 17 x size 16, 4 x size 12 | 15 x 7.5 A outputs (boards A1, A2; A2 OUT2 feeds the fans inside) + 4 x 15 A outputs (board B OUT5-8) |
| X2 | HDP24-24-47SE-L017 (sockets) | HDP26-24-47PE-L015 (pins) | 24-47: 42 x size 20, 5 x size 16 | inputs, analog, CAN, signal GND |
| - | copper bosses / risers through the lid | ring terminals | - | 150 A battery feed (+12 V) and chassis ground on M6 copper bosses; board B OUT1-4 (31 A each) on M4 copper offset risers on T1-T4 (b4a, d1a; parts in `docs/enclosure-v2b.md`) |

## X1 - outputs: boards A1 and A2 (size 16, 16 AWG) and board B OUT5-8 (size 12, 14 AWG)

Insert 24-21. Size 12 cavities are B, D, E, G (inner big ring), and the other 17 are size 16. Outputs go around the outer ring, clockwise from H in the rear view.

| Cavity | Signal | Board connector | Cavity | Signal | Board connector |
|---|---|---|---|---|---|
| H | A1_OUT1 | A1 J3 pad 8 (O1) | S | A2_OUT1 | A2 J3 pad 8 (O1) |
| J | A1_OUT2 | A1 J3 pad 7 (O2) | T | spare: A2_OUT2 drives the fans inside the box (r7a) | A2 J3 pad 7 (O2) wired to both fans, not to X1 |
| K | A1_OUT3 | A1 J3 pad 10 (O3) | U | A2_OUT3 | A2 J3 pad 10 (O3) |
| L | A1_OUT4 | A1 J3 pad 9 (O4) | V | A2_OUT4 | A2 J3 pad 9 (O4) |
| M | A1_OUT5 | A1 J3 pad 6 (O5) | W | A2_OUT5 | A2 J3 pad 6 (O5) |
| N | A1_OUT6 | A1 J3 pad 5 (O6) | X | A2_OUT6 | A2 J3 pad 5 (O6) |
| P | A1_OUT7 | A1 J3 pad 4 (O7) | A | A2_OUT7 | A2 J3 pad 4 (O7) |
| R | A1_OUT8 | A1 J3 pad 3 (O8) | C | A2_OUT8 | A2 J3 pad 3 (O8) |

| Cavity | Signal | Board connector |
|---|---|---|
| B | B_OUT5 (15 A) | B terminal T5 |
| D | B_OUT6 (15 A) | B terminal T6 |
| E | B_OUT7 (15 A) | B terminal T7 |
| G | B_OUT8 (15 A) | B terminal T8 |

B, D, E, G are the size 12 cavities (25 A). Spare: F and T (size 16; T since r7a, fan output choice in `docs/firmware-thermal-plan.md`). Plug every unused cavity with a sealing plug.

## X2 - inputs, analog, CAN (size 20, 20 AWG)

Insert 24-47 is numbered 1-47 in a spiral, with 1 at the center. The size 16 cavities are **1, 4, 5, 6, 34**, all left as spares. The other 42 are size 20.
The drawing labels only some numbers (1, 2, 20, 30, 40, 47); the rest come from tracing its numbering line. Check them against the numbers molded on the part before crimping.

| Cavity | Signal | Source inside the box |
|---|---|---|
| 2, 3 | CAN_H, CAN_L | CAN bus to the Link ECU (twisted pair; daisy-chained inside the box) |
| 7, 8 | A1_IN1, A1_IN2 | board A1 J3 pads 12 (I1), 11 (I2) |
| 9-13 | A1_IN3 .. A1_IN7 | input board #1 J2 pins 1-5 |
| 14 | A1_AN | input board #1 J2 pin 9 (0-5 V) |
| 15, 16 | A2_IN1, A2_IN2 | board A2 J3 pads 12 (I1), 11 (I2) |
| 17-21 | A2_IN3 .. A2_IN7 | input board #2 J2 pins 1-5 |
| 22 | A2_AN | input board #2 J2 pin 9 |
| 23, 24 | B_IN1, B_IN2 | board B stock inputs |
| 25-32 | B_IN3 .. B_IN10 | input board #3 J2 pins 1-8 |
| 33 | B_AN | input board #3 J2 pin 9 |
| 35-38 | SIG_GND | signal ground (switch/sensor returns), from input boards J2 pins 10-12 |
| 39-47 | spare | 9 x size 20 |
| 1, 4, 5, 6, 34 | spare | 5 x size 16 |

33 used, 14 spare.

## Power terminals (bosses and risers)

Dan, 2026-11-09: no X3 connector. One pin per output on enclosure connectors (no ganged pins), and no HD30/HDP shell-24 insert has four cavities above 25 A.
The separate studs planned on 2026-11-09 are replaced by copper bosses and offset risers that show through the lid (b4a, d1a); design and parts: `docs/enclosure-v2b.md`.

| Terminal | Signal | Current |
|---|---|---|
| BATT boss | +12 V feed from the battery | 150 A |
| GND boss | chassis ground | - |
| OUT1 .. OUT4 risers | board B OUT1-4 (BTS70012), on board terminals T1-T4 | 31 A each |

## Contacts needed vs on hand

| Size | Needed (pins + sockets) | On hand | Buy |
|---|---|---|---|
| 20 | 33 + 33 | none | yes, about 70 total plus spares |
| 16 | 15 + 15 | plenty (16-20 AWG and 14 AWG) | no |
| 12 | 4 + 4 | 20 + 20 | no |

Also buy: sealing plugs for spare cavities (size 20, 16). The HDP 24-9 set is not used.

## Notes
- X2 size 16 cavity numbers (1, 4, 5, 6, 34): check them against the part's molded numbers before crimping.
- Other open items (contacts to buy, current checks): `STATE.md`, Open items (hardware). Pictures: `docs/diagrams/` (illustrations, not a source of truth).
