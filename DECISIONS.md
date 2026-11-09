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

## CAN
- 2026-11-08 (Dan, chat): CAN bus runs at 1 Mbps.
- 2026-11-08 (Dan, chat): CAN termination is install-specific (out of scope); every board keeps a selectable 120 ohm termination jumper.
- 2026-11-08 (Dan, chat): Any CAN device (e.g. a keypad) can join later; it must use 1 Mbps and IDs that don't collide with the PDM boards.
