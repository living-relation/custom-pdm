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
T1-T4 straps (REDCUBE 74650074R body is 3.0 mm tall).

## Overview

| # | Box side (panel) | Harness side | Insert | Carries |
|---|---|---|---|---|
| X1 | HD34-24-21SN (aluminum, flange, sockets) | HD36-24-21PN (pins) | 24-21: 17 x size 16, 4 x size 12 | 15 x 7.5 A outputs (boards A1, A2; A2 OUT2 feeds the fans inside) + 4 x 15 A outputs (board B OUT5-8) |
| X2 | HDP24-24-47SE-L017 (sockets) | HDP26-24-47PE-L015 (pins) | 24-47: 42 x size 20, 5 x size 16 | inputs, analog, CAN, signal GND |
| - | 6 studs | ring terminals | - | 150 A battery feed (+12 V); chassis ground; board B OUT1-4 (31 A each, one stud per output, rubber boots) |

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
| 25-32 | B_IN3 .. B_IN10 | input board #3 J2 pins 1-8 (board B pin count to confirm) |
| 33 | B_AN | input board #3 J2 pin 9 |
| 35-38 | SIG_GND | signal ground (switch/sensor returns), from input boards J2 pins 10-12 |
| 39-47 | spare | 9 x size 20 |
| 1, 4, 5, 6, 34 | spare | 5 x size 16 |

33 used, 14 spare.

## Studs

Dan, 2026-11-09: no X3 connector. One pin per output on enclosure connectors (no ganged pins), and no HD30/HDP shell-24 insert has four cavities above 25 A.

| Stud | Signal | Current |
|---|---|---|
| BATT | +12 V feed from the battery | 150 A |
| GND | chassis ground | - |
| OUT1 .. OUT4 | board B OUT1-4 (BTS70012), from board terminals T1-T4 | 31 A each |

Output studs are live when their output is on: fit rubber boots.

## Contacts needed vs on hand

| Size | Needed (pins + sockets) | On hand | Buy |
|---|---|---|---|
| 20 | 33 + 33 | none | yes, about 70 total plus spares |
| 16 | 16 + 16 | plenty (16-20 AWG and 14 AWG) | no |
| 12 | 4 + 4 | 20 + 20 | no |

Also buy: 6 studs with boots, sealing plugs for spare cavities (size 20, 16). The HDP 24-9 set is not used.

## Open items
- X2 size 16 cavity numbers (1, 4, 5, 6, 34): check them against the part's molded numbers.
- Board B input count (dingoPDM-Max spare pins: about 8-9 fan out cleanly; confirm when board B is built).
- X1 current (checked 2026-11-09): TE's HD30/HDP20 catalog and technical manual give only per-contact ratings (continuous at 125 C) and no total-connector limit or multi-contact derating. Loads here are 7.5 A on size 16 (13 A) and 15 A on size 12 (25 A), about 60% of each contact's rating. Dan: per-contact rating is the criterion; the enclosure gets ample cooling.
- Board B terminals are all REDCUBE 74650074R (50 A at 20 C); OUT1-4 carry 31 A (62%). Dan: per-contact rating is the criterion. Pictures: `docs/diagrams/` (illustrations, not a source of truth).
