# Box connectors (enclosure wall)

Decisions: Dan, 2026-11-09 (see DECISIONS.md). TE Deutsch HD30 / HDP20 parts already on hand.
Cavity numbers are filled in from TE's insert drawings (pending): until then each signal only has a contact-size group.

Contact ratings (TE Deutsch common contact system, max at 125 C continuous): size 20 = 7.5 A (16-20 AWG),
size 16 = 13 A (14-20 AWG), size 12 = 25 A (12-14 AWG), size 8 = 60 A (8-10 AWG), size 4 = 100 A (6 AWG).

## Overview

| # | Box side (panel) | Harness side | Insert | Carries |
|---|---|---|---|---|
| X1 | HD34-24-21SN (aluminum, flange, sockets) | HD36-24-21PN (pins) | 24-21: 17 x size 16, 4 x size 12 | 16 x 7.5 A outputs (boards A1, A2) |
| X2 | HDP24-24-47SE-L017 (sockets) | HDP26-24-47PE-L015 (pins) | 24-47: 42 x size 20, 5 x size 16 | inputs, analog, CAN, signal GND |
| X3 | HDP24-24-9PE (pins) | HDP26-24-9SE (sockets) | 24-9: 6 x size 12, 2 x size 8, 1 x size 4 | board B 6 x 15 A + 2 x 30 A |
| - | stud | ring terminal | - | 150 A battery feed (+12 V); chassis ground stud |

Live outputs sit on socket contacts on the box side for X1 and X2. X3's on-hand receptacle has pins (see open items).

## X1 - outputs, boards A1 and A2 (size 16, 16 AWG)

| Signal | Board | Board connector | Contact | Wire |
|---|---|---|---|---|
| A1_OUT1 .. A1_OUT8 | A1 | J3 pins 8, 7, 10, 9, 6, 5, 4, 3 (OUT1..OUT8) | size 16 | 16 AWG |
| A2_OUT1 .. A2_OUT8 | A2 | J3 pins 8, 7, 10, 9, 6, 5, 4, 3 | size 16 | 16 AWG |
| spare | - | - | 1 x size 16, 4 x size 12 | - |

## X2 - inputs, analog, CAN (size 20, 20 AWG)

| Signal | Count | Source inside the box |
|---|---|---|
| A1_IN1, A1_IN2 | 2 | board A1 J3 pins 12, 11 |
| A1_IN3 .. A1_IN7 | 5 | input board #1 J2 pins 1-5 |
| A1_AN | 1 | input board #1 J2 pin 9 (0-5 V) |
| A2_IN1, A2_IN2 | 2 | board A2 J3 pins 12, 11 |
| A2_IN3 .. A2_IN7 | 5 | input board #2 J2 pins 1-5 |
| A2_AN | 1 | input board #2 J2 pin 9 |
| B_IN1, B_IN2 | 2 | board B stock inputs |
| B_IN3 .. B_IN10 | up to 8 | input board #3 J2 pins 1-8 (board B pin count to confirm) |
| B_AN | 1 | input board #3 J2 pin 9 |
| CAN_H, CAN_L | 2 | CAN bus to the Link ECU (daisy-chained inside the box) |
| SIG_GND | 4 | signal ground (switch/sensor returns), from input boards J2 pins 10-12 |
| **Total** | **~33** | of 47 (14 spare, incl. 5 x size 16) |

## X3 - board B high current

| Signal | Count | Contact | Wire |
|---|---|---|---|
| B_OUT 15 A | 6 | size 12 (25 A) | 14 AWG (12 AWG for long runs) |
| B_OUT 30 A | 2 | size 8 (60 A) | 10 AWG |
| spare | 1 | size 4 | - |

## Contacts needed vs on hand

| Size | Needed (pins + sockets) | On hand | Buy |
|---|---|---|---|
| 20 | ~33 + ~33 | none | yes, plus spares |
| 16 | 17 + 17 | plenty (16-20 AWG and 14 AWG) | no |
| 12 | 6 + 6 | 20 + 20 | no |
| 8 | 2 + 2 | 5 + 9 | no |

## Open items
- X2 part numbers assume the spare 47-way set is HDP24-24-47SE-L017 + HDP26-24-47PE-L015 (Dan: one set is spare; confirm which).
- Cavity numbers per signal: from TE drawings HD34-24-21SN, HDP24-24-47SE, HDP24-24-9PE.
- X3: the on-hand receptacle HDP24-24-9PE has pins, so the box would show live pins when unplugged. The outputs are off unless commanded, but a socket-side receptacle (HDP24-24-9SE) is the usual choice for a power source.
- Board B input count (dingoPDM-Max spare pins: about 8-9 fan out cleanly; confirm when board B is built).
