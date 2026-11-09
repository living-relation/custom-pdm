# DECISIONS - custom-pdm

One dated line per decision, newest last. Who decided, then where it came from.

## Scope and architecture
- 2026-11-05 (Dan, chat): Personal project, not for sale. Bigger dingoPDM-based PDM (dingoPDM by Cory Grant, MIT) for car accessories, not high-current pumps or motors.
- 2026-11-05 (Dan, chat): 12 V system, about 150 A total feed. 24 outputs: 16 x 8 A, 6 x 15 A, 2 x 30 A (30 A outputs may be flying leads).
- 2026-11-05 (Dan, chat): 16 universal 0-5 V inputs, usable as digital by firmware threshold.
- 2026-11-08 (Dan, chat): Replaces the line above: inputs are on/off, not sensor inputs. Each input works as switch-to-ground or 12 V on/off, chosen per input in firmware. No 5 V sensor supply. Board A: 2 existing + 8 new inputs.
- 2026-11-08 (Dan, chat): Future 5 V analog sensors, if ever needed, come in through external hardware (e.g. the Link ECU's own analog inputs sent over CAN); keep the spare analog pin reachable.
- 2026-11-05 (Dan, chat): Controlled over CAN by a Link G4X XtremeX ECU; the ECU can send anything over CAN, so no CAN map work is needed up front.
- 2026-11-05 (Dan, chat): Plan B (3 boards on CAN, one enclosure) leads; Plan C (one brain + power slices) stays open until one clearly wins.
- 2026-11-05 (Dan, chat): Plan B uses two board designs: board A (8 x 8 A outputs + 8 inputs, built twice) and board B (6 x 15 A + 2 x 30 A).
- 2026-11-05 (Dan, chat): Connectors: Deutsch DT-style for 8 A outputs; screw terminals or studs for 15 A and 30 A outputs. Sealed enclosure.
- 2026-11-05 (Dan, chat): Fab and assembly: JLCPCB and PCBWay both stay in the running until one clearly wins.

## Tools and workflow
- 2026-11-05 (Dan, chat): CAD is Autodesk Fusion with Electronics, starting from the dingoPDM v7.5 (board A) and dingoPDM-Max (board B) KiCad sources. Dan does not do PCB design; Claude plans and drives the tools.
- 2026-11-07 (Dan, chat): Fusion project is `custom-pdm`; finished exports go to the OneDrive models folder (`Desktop\models`, add-only).
- 2026-11-08 (Dan, chat): KiCad files in this repo are the design source, edited by scripts in `tools/` and checked with KiCad ERC/DRC; Fusion is used to view, review and later for 3D (re-import after each round).
- 2026-11-08 (Claude, PR #3): The board A PCB stays in KiCad 9 format (KiCad 9.0.8 edits it) because Fusion's importer loses all nets from a KiCad 10 PCB.
- 2026-11-08 (Dan, chat): Agents may merge their own PRs when green (no CI = GitHub shows mergeable/clean).
- 2026-11-08 (Dan, chat): Install the git-checker state-file check as a PR workflow in comment mode (warns, never blocks).
- 2026-11-08 (Dan, chat): Agents click app dialogs (e.g. Fusion import) themselves with screen control instead of asking Dan.

## Heat and enclosure
- 2026-11-05 (Claude, chat; Dan agreed): Add an aluminum heat-spreader plate (about 25 W worst case).
- 2026-11-05 (Dan, chat): Enclosure is MJF 3D printed.
- 2026-11-08 (Dan, chat): PDM mounts inside the cabin (design air temp up to about 60 C). Enclosure: aluminum, or MJF print with a heat sink; thermal pads, small fan allowed.
- 2026-11-08 (Dan, chat): 8 A outputs are limited to 7.5 A (BTS7008-2EPA rating, all channels on at 85 C).
- 2026-11-08 (Dan, chat): Heat checks: hand calc now, Elmer 3D model (handbuilt-cad sim stack) once the layout exists. No Fusion thermal study.

## Board A
- 2026-11-08 (Dan, chat): Replace the two BTS7002 singles (U8, U9) with one BTS7008-2EPA dual at U8, keeping 8 outputs per board.
- 2026-11-08 (Dan, chat): Re-pin J3 so the dual sits between its two output pins: pin 7 = OUT2, pin 8 = OUT1 (was IN1), pin 12 = IN1 (was OUT2). Signal wires routed by script.
- 2026-11-08 (Claude, finding): BTS7002-1EPP and BTS7008-2EPA share the TSDSO-14 footprint and pins 1-4 (GND, IN/IN0, DEN, IS) and 15 (VS); the dual adds DSEL (pad 5) and IN1 (pad 6) and splits outputs (pads 12-14 OUT0, 8-10 OUT1).
- 2026-11-08 (Dan, chat): Board A's 8 new inputs live on a small input daughter board: board A's 8 free MCU pins go to a header, keyed ribbon cable to the input board, which holds the input protection parts and a Deutsch DT 12-pin connector.
- 2026-11-08 (Dan, chat): Input pull resistors: per input a 10 kohm pull-up (to 3.3 V) and a 10 kohm pull-down, each on a DIP switch (up / down / off); off falls back to the MCU's weak pull. Per input also the dingo filter: 4.7 kohm series, BAT54S clamp, 10 nF.
- 2026-11-08 (Dan, chat): Board A to input board link: JST GH 12-pin locking connector (J6, side entry) at the left board edge, replacing the keyed ribbon header. J6: 1-8 IN_3..IN_10, 9 spare analog (PC2), 10 +3.3 V, 11-12 GND.
- 2026-11-08 (Claude, finding): PC2 (spare analog) reaches the old IS2 buffer only through R12; R12 set DNP frees it. A 2.54 mm 2x6 header does not fit near the MCU; J6 (19.6 x 6.7 mm) fits only at the left edge turned sideways.
- 2026-11-08 (Dan, chat): Inputs reach the MCU on its free pins directly (no I2C expander): rework the copper around U4 to free them instead.
- 2026-11-08 (Claude, finding): At board rules (0.2/0.2 mm, 0.8 mm vias) only 1 of the 9 spare U4 pins can fan out; the left-edge row (pins 53-59: CAN_STANDBY, IN_10, SWO, IN_5, IN_6, I2C SCL, SDA) cannot all get vias. Open question A4 (re-fan the row, drop SWO, fewer pins, or expander) and Dan's idea of enlarging the board.
- 2026-11-08 (Dan, chat): Input board's Deutsch DT 12-pin is a panel-mount receptacle in the enclosure wall with short wires to the input board (not a PCB-mount DT header, whose panel cutout is about 49 x 42 mm).
- 2026-11-08 (Dan, chat): Heat sink: the board is pressed onto it by a center standoff between the two driver-chip pairs (no board change). Back copper under the drivers is +12 V, so the thermal pad must be electrically insulating; J3's through-hole pins need a pocket in the heat sink.
- 2026-11-08 (Dan, chat): Remove all test points on board A (TP1-TP3, TP5, TP6, TP8-TP10). PC10, PC11, PC13 (ex E1-E3) become inputs.
- 2026-11-08 (Dan, chat): Drop SWO (trace output); PB3 becomes an input. Programming/debug via SWCLK/SWDIO is unchanged.
- 2026-11-08 (Claude, finding): Patching dingo's layout around U4 frees at most 5 new input pins (PC10, PC11, PC13, PB3, PB4) without disturbing dingo's own signals; more needs a re-layout of the U4 area.
- 2026-11-08 (Dan, chat): Board A gets 5 new inputs (PC10, PC11, PB4, PC13, PB3); J6 stays 12-pin with pins 6-8 unused so one input board design also fits board B.
- 2026-11-08 (Dan, chat): Board B (dingoPDM-Max) gets its extra inputs too: plan about 9 new (decide the final count when board B is built).

## CAN
- 2026-11-08 (Dan, chat): CAN bus runs at 1 Mbps.
- 2026-11-08 (Dan, chat): CAN termination is install-specific (out of scope); every board keeps a selectable 120 ohm termination jumper.
- 2026-11-08 (Dan, chat): Any CAN device (e.g. a keypad) can join later; it must use 1 Mbps and IDs that don't collide with the PDM boards.
