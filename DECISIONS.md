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

- 2026-11-09 (Dan, chat): Remove dingo's DRT logo (G1) from board A; J6 sits where it was.
- 2026-11-09 (Dan, chat): Input board has as many channels as possible: 8 digital + 1 analog (board A uses 5, board B up to 8).
- 2026-11-09 (Dan, chat): Input board wires connect with a Molex Micro-Fit 3.0 2x6 (crimped, locking).
- 2026-11-09 (Dan, chat): The analog channel takes 0-5 V (divider + clamp).
- 2026-11-09 (Dan, chat): Box connectors: cheaper plastic circular (HD-style or similar) instead of Deutsch DT; two connectors or fewer for the whole box, carrying all low-current I/O (7.5 A outputs, inputs, analog). High-current outputs use separate studs.

- 2026-11-09 (Dan, chat): Box connectors are TE Deutsch HD30/HDP20 family (not CPC), using parts already on hand: X1 outputs = HD30 24-21 (HD34-24-21SN / HD36-24-21PN), X2 signals = a spare HDP 24-47 set, X3 board B 15 A/30 A outputs = HDP 24-9 (instead of studs). 150 A feed stays on a stud.
- 2026-11-09 (Dan, chat): Leave the ST185 project's TE on-hand list unchanged (don't mark parts claimed there).
- 2026-11-09 (Dan, chat): Fusion work (import, check, render) never needs asking.
- 2026-11-09 (Dan, chat, standing): Anything that sources power has socket contacts on the box side, so X3 becomes HDP24-24-9SE (buy) with the on-hand HDP26-24-9PE plug.
- 2026-11-09 (Dan, chat, standing): Manufacturer drawings and datasheets can be downloaded without asking.
- 2026-11-09 (Dan, chat): X2 is HDP24-24-47SE-L017 (box) + HDP26-24-47PE-L015 (harness).
- 2026-11-09 (Dan, chat): Board B gets 8 outputs and extra inputs (D1b). Superseded the same day by F1a: no add-on ADC; the 4 new BTS7004 channels and 9 extra inputs use the MCU's spare pins. That gives board B 11 inputs and the system about 25.
- 2026-11-09 (Dan, chat): Board B keeps all 4 stock BTS70012 (G1a): 4 x 31 A + 4 x 15 A, no software current cap; connectors must carry full current.
- 2026-11-09 (Dan, chat): Board B is one bigger board, not a base board plus add-on (G2a).
- 2026-11-09 (Dan, chat): OUT1-4 leave board B on bolt-down terminals, one wire per output, instead of ganged DT pins (I1a).
- 2026-11-09 (Dan, chat, standing): No ganged (paralleled) pins on enclosure connectors: one pin per output.
- 2026-11-09 (Dan, chat): X3 (HDP 24-9) dropped. Board B OUT5-8 (15 A) go to X1's size 12 cavities B, D, E, G; board B's big outputs go to studs (OUT1-3 stated; OUT4 too, since it never fit X3).
- 2026-11-09 (Dan, chat): Board B OUT5-8 also leave the board on bolt-down terminals, one wire per output (J1a). OUT4 goes to a stud like OUT1-3 (L1a): 4 output studs.
- 2026-11-09 (Dan, chat): Connector diagrams are saved in `docs/diagrams/` as illustrations only, not a source of truth.
- 2026-11-09 (Dan, chat): Board B's CAN + IN1-2 connector is a Molex Micro-Fit 2x2 (M1a).
- 2026-11-09 (Dan, chat): Connector current criterion: each pin must meet its own load within the maker's per-contact rating; no extra total-connector derating. The enclosure gets more than enough cooling.
- 2026-11-09 (Dan, chat): Personal project, not for sale. The repo becomes local-only (detached from GitHub; Dan made the GitHub repo private instead of deleting it, kept detached for now) so dingoPDM-Max files (no license) can sit with the rest.

## CAN
- 2026-11-08 (Dan, chat): CAN bus runs at 1 Mbps.
- 2026-11-08 (Dan, chat): CAN termination is install-specific (out of scope); every board keeps a selectable 120 ohm termination jumper.
- 2026-11-08 (Dan, chat): Any CAN device (e.g. a keypad) can join later; it must use 1 Mbps and IDs that don't collide with the PDM boards.

## Pin map and enclosure questions (asked one at a time from 2026-11-10)
- 2026-11-10 (Dan, chat): B1 - board B input B_IN5 sits on PB2 (BOOT1, a startup pin). Try moving it to the spare PC13 now, before the board is ordered. If the reroute is too risky, keep PB2 and live with the rule (that input off during a USB firmware update). If a firmware-update UI is involved, it should warn to disconnect or switch off whatever is needed.
- 2026-11-10 (Dan, chat): B2 - wake-up from sleep: CAN and USB only by default (no switch input wakes the PDM); each input can be switched on as a wake source by the user, per channel. Limit to respect: two pins with the same pin number share one wake line, so only one input of such a pair can be a wake source (pairs: `STATE.md`, orchestrator section).

## Firmware and coordination
- 2026-11-10 (Dan, chat): The three boards must act as one PDM. Approach: stock dingoFW logic on every board plus a PC-side single-PDM layer (A3a); new "front door" firmware is the backup.
- 2026-11-10 (Dan, chat): Nothing goes upstream to dingoPDM / dingoFW. Firmware lives in `firmware/` in this repo: dingoFW copied in, ChibiOS kept as a git-ignored local clone (B2a).
- 2026-11-10 (Dan, chat): Firmware and simulation work stays on a feature branch or in a sandbox. Do not merge it.
- 2026-11-10 (Dan, chat): CAN address: three firmware builds (A unit 1, A unit 2, B) with address and 1 Mbit/s built in by default; setting a board up by hand over CAN stays possible at any time (C1a + b).
- 2026-11-10 (Dan, chat): Link loss: chosen per channel in the config, default Off, and including a retry mode (C2a). Branch reading of "retry mode": overcurrent reset mode defaults to Count (3 tries) in the custom builds; confirm.
- 2026-11-10 (Dan, chat): Keep the four small firmware choices for now (C3a: status frame 27, wake-up set, `LINE_UNUSED` = PC13 on board B, analog scaling), guided by the Session 2 pin-map research.
- 2026-11-10 (Dan, chat): Simulation order: compile, then host-side logic tests, then Renode if feasible (C4a). Renode goes in a sandbox on DansPC (WSL).
- 2026-11-10 (Claude, finding): Renode 1.17.0 boots the board A binary on its stock `stm32f4` platform (CAN model present). Missing for a full run: I2C FRAM, MCP9808 and ADC models.
- 2026-11-10 (Dan, chat): D1: "retry mode" means both. Overcurrent: retry 3 times before Fault (default in the custom builds). Lost link: outputs follow commands again by themselves when messages return (stock behaviour, shown in `s1_system.py`).
- 2026-11-10 (Dan, chat): D2a: build the full Renode bench, time-boxed.
- 2026-11-10 (Dan, chat): F1: open questions and notes between sessions live in a shared non-repo folder, `C:\projects\_scratch\custom-pdm-shared\` (`SESSION-BOARD.md`), which Dan attaches to the Claude project. `STATE.md` is a shared document: point to it, never copy from it.
- 2026-11-10 (Dan, chat): D3a: default link-loss time-out is 1 s, adjustable. (1 s is also the stock firmware default for a CAN input; range 0 to 60 s per input.)
- 2026-11-10 (Dan, chat): D4a: CAN IDs 0x500 / 0x520 / 0x540 are fine for now and must stay user-editable (they are: device parameter over CAN / USB).
- 2026-11-10 (Dan, chat): D5: research options for the PC-side single-PDM layer, or use Dan's existing design (which design: open).
- 2026-11-10 (Dan, chat): The shared non-repo folder / session board idea (F1) is dropped, and so is the "also update the shared document on every state update" rule. `STATE.md` stays the shared document and the one place for open questions and handoffs.
- 2026-11-10 (Dan, chat): Merge everything on `feat/firmware` into `main` (replaces "do not merge" from earlier the same day).
- 2026-11-10 (Dan, chat): D5 closed. Dan has no PC-side layer built as far as he knows; a check of everything on `main` found none (hardware, board scripts and docs only; `reference/` holds the stock KiCad projects). So: research options and bring Dan choices (D5a).

## Orchestration and backup
- 2026-11-10 (Dan, chat): A1a - one orchestrator session now owns both the hardware / enclosure job and the firmware / simulation job. It deploys sub-agents, reviews all their work, keeps state, tracking and memory current, manages PRs, keeps local and remote in sync, and reports everything to Dan in one place. It researches in the repo before asking Dan anything.
- 2026-11-10 (Dan, chat): A5a - re-attach the private GitHub repo `living-relation/custom-pdm` as the remote, as an off-PC backup. Replaces "local-only" (2026-11-09) once the remote is attached.
- 2026-11-10 (Dan, chat): A2a - the docs sweep (iterative-cleaning, report-only) waits until the enclosure questions are answered. A3a - stale working-memory lines get fixed. A4a - work order: goal 1 fixes and the Renode bench in parallel, open questions to Dan one at a time.
- 2026-11-11 (Dan, chat): B3a - output dimming / pulsing (PWM) stays the stock software method; no hardware-timer PWM, so no IN-pin moves for timers (`docs/firmware-pin-map.md` section 9, Q3).
