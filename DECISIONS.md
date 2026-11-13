# DECISIONS - custom-pdm

One dated line per decision, newest last. Who decided, then where it came from.

## Scope and architecture
- 2026-11-05 (Dan, chat): Personal project, not for sale. Bigger dingoPDM-based PDM (dingoPDM by Cory Grant, MIT) for car accessories, not high-current pumps or motors.
- 2026-11-05 (Dan, chat): 12 V system, about 150 A total feed. 24 outputs: 16 x 8 A, 6 x 15 A, 2 x 30 A (30 A outputs may be flying leads). (output mix replaced 2026-11-08 / 2026-11-09: 7.5 A limit, G1a)
- 2026-11-05 (Dan, chat): 16 universal 0-5 V inputs, usable as digital by firmware threshold. (replaced 2026-11-08, next line)
- 2026-11-08 (Dan, chat): Replaces the line above: inputs are on/off, not sensor inputs. Each input works as switch-to-ground or 12 V on/off, chosen per input in firmware. No 5 V sensor supply. Board A: 2 existing + 8 new inputs.
- 2026-11-08 (Dan, chat): Future 5 V analog sensors, if ever needed, come in through external hardware (e.g. the Link ECU's own analog inputs sent over CAN); keep the spare analog pin reachable.
- 2026-11-05 (Dan, chat): Controlled over CAN by a Link G4X XtremeX ECU; the ECU can send anything over CAN, so no CAN map work is needed up front.
- 2026-11-05 (Dan, chat): Plan B (3 boards on CAN, one enclosure) leads; Plan C (one brain + power slices) stays open until one clearly wins. (Plan C closed 2026-11-11: b3a)
- 2026-11-05 (Dan, chat): Plan B uses two board designs: board A (8 x 8 A outputs + 8 inputs, built twice) and board B (6 x 15 A + 2 x 30 A). (board B outputs replaced 2026-11-09: G1a, F1a)
- 2026-11-05 (Dan, chat): Connectors: Deutsch DT-style for 8 A outputs; screw terminals or studs for 15 A and 30 A outputs. Sealed enclosure. (connectors replaced 2026-11-09: HD30/HDP20, studs, terminals)
- 2026-11-05 (Dan, chat): Fab and assembly: JLCPCB and PCBWay both stay in the running until one clearly wins.

## Tools and workflow
- 2026-11-05 (Dan, chat): CAD is Autodesk Fusion with Electronics, starting from the dingoPDM v7.5 (board A) and dingoPDM-Max (board B) KiCad sources. Dan does not do PCB design; Claude plans and drives the tools.
- 2026-11-07 (Dan, chat): Fusion project is `custom-pdm`; finished exports go to the OneDrive models folder (`Desktop\models`, add-only).
- 2026-11-08 (Dan, chat): KiCad files in this repo are the design source, edited by scripts in `tools/` and checked with KiCad ERC/DRC; Fusion is used to view, review and later for 3D (re-import after each round).
- 2026-11-08 (Claude, PR #3): The board A PCB stays in KiCad 9 format (KiCad 9.0.8 edits it) because Fusion's importer loses all nets from a KiCad 10 PCB.
- 2026-11-08 (Dan, chat): Agents may merge their own PRs when green (no CI = GitHub shows mergeable/clean). (CI exists since 2026-11-08: the state-check workflow)
- 2026-11-08 (Dan, chat): Install the git-checker state-file check as a PR workflow in comment mode (warns, never blocks).
- 2026-11-08 (Dan, chat): Agents click app dialogs (e.g. Fusion import) themselves with screen control instead of asking Dan.

## Heat and enclosure
- 2026-11-05 (Claude, chat; Dan agreed): Add an aluminum heat-spreader plate (about 25 W worst case). (heat estimate replaced 2026-11-10: 31.1 W hand calc, `docs/enclosure-layout.md` 4.3)
- 2026-11-05 (Dan, chat): Enclosure is MJF 3D printed. (replaced 2026-11-08, next line)
- 2026-11-08 (Dan, chat): PDM mounts inside the cabin (design air temp up to about 60 C). Enclosure: aluminum, or MJF print with a heat sink; thermal pads, small fan allowed.
- 2026-11-08 (Dan, chat): 8 A outputs are limited to 7.5 A (BTS7008-2EPA rating, all channels on at 85 C).
- 2026-11-08 (Dan, chat): Heat checks: hand calc now, Elmer 3D model (handbuilt-cad sim stack) once the layout exists. No Fusion thermal study.

## Board A
- 2026-11-08 (Dan, chat): Replace the two BTS7002 singles (U8, U9) with one BTS7008-2EPA dual at U8, keeping 8 outputs per board.
- 2026-11-08 (Dan, chat): Re-pin J3 so the dual sits between its two output pins: pin 7 = OUT2, pin 8 = OUT1 (was IN1), pin 12 = IN1 (was OUT2). Signal wires routed by script.
- 2026-11-08 (Claude, finding): BTS7002-1EPP and BTS7008-2EPA share the TSDSO-14 footprint and pins 1-4 (GND, IN/IN0, DEN, IS) and 15 (VS); the dual adds DSEL (pad 5) and IN1 (pad 6) and splits outputs (pads 12-14 OUT0, 8-10 OUT1).
- 2026-11-08 (Dan, chat): Board A's 8 new inputs live on a small input daughter board: board A's 8 free MCU pins go to a header, keyed ribbon cable to the input board, which holds the input protection parts and a Deutsch DT 12-pin connector. (link replaced 2026-11-08 by JST GH; wire connector replaced 2026-11-09 by Molex Micro-Fit)
- 2026-11-08 (Dan, chat): Input pull resistors: per input a 10 kohm pull-up (to 3.3 V) and a 10 kohm pull-down, each on a DIP switch (up / down / off); off falls back to the MCU's weak pull. Per input also the dingo filter: 4.7 kohm series, BAT54S clamp, 10 nF.
- 2026-11-08 (Dan, chat): Board A to input board link: JST GH 12-pin locking connector (J6, side entry) at the left board edge, replacing the keyed ribbon header. J6: 1-8 IN_3..IN_10, 9 spare analog (PC2), 10 +3.3 V, 11-12 GND. (pins 1-5 used, 6-8 NC since 2026-11-08: 5 new inputs)
- 2026-11-08 (Claude, finding): PC2 (spare analog) reaches the old IS2 buffer only through R12; R12 set DNP frees it. A 2.54 mm 2x6 header does not fit near the MCU; J6 (19.6 x 6.7 mm) fits only at the left edge turned sideways.
- 2026-11-08 (Dan, chat): Inputs reach the MCU on its free pins directly (no I2C expander): rework the copper around U4 to free them instead.
- 2026-11-08 (Claude, finding): At board rules (0.2/0.2 mm, 0.8 mm vias) only 1 of the 9 spare U4 pins can fan out; the left-edge row (pins 53-59: CAN_STANDBY, IN_10, SWO, IN_5, IN_6, I2C SCL, SDA) cannot all get vias. Open question A4 (re-fan the row, drop SWO, fewer pins, or expander) and Dan's idea of enlarging the board. (A4 settled 2026-11-08: 5 new inputs)
- 2026-11-08 (Dan, chat): Input board's Deutsch DT 12-pin is a panel-mount receptacle in the enclosure wall with short wires to the input board (not a PCB-mount DT header, whose panel cutout is about 49 x 42 mm). (replaced 2026-11-09: box connectors X1/X2)
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
- 2026-11-09 (Dan, chat): Box connectors: cheaper plastic circular (HD-style or similar) instead of Deutsch DT; two connectors or fewer for the whole box, carrying all low-current I/O (7.5 A outputs, inputs, analog). High-current outputs use separate studs. (replaced the same day: TE HD30/HDP20, next line)

- 2026-11-09 (Dan, chat): Box connectors are TE Deutsch HD30/HDP20 family (not CPC), using parts already on hand: X1 outputs = HD30 24-21 (HD34-24-21SN / HD36-24-21PN), X2 signals = a spare HDP 24-47 set, X3 board B 15 A/30 A outputs = HDP 24-9 (instead of studs). 150 A feed stays on a stud. (X3 dropped later on 2026-11-09)
- 2026-11-09 (Dan, chat): Leave the ST185 project's TE on-hand list unchanged (don't mark parts claimed there).
- 2026-11-09 (Dan, chat): Fusion work (import, check, render) never needs asking.
- 2026-11-09 (Dan, chat, standing): Anything that sources power has socket contacts on the box side, so X3 becomes HDP24-24-9SE (buy) with the on-hand HDP26-24-9PE plug. (X3 dropped later on 2026-11-09; the socket rule stands)
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
- 2026-11-09 (Dan, chat): Personal project, not for sale. The repo becomes local-only (detached from GitHub; Dan made the GitHub repo private instead of deleting it, kept detached for now) so dingoPDM-Max files (no license) can sit with the rest. (local-only replaced 2026-11-10: A5a)

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
- 2026-11-10 (Dan, chat): Firmware and simulation work stays on a feature branch or in a sandbox. Do not merge it. (replaced the same day: merge into `main`)
- 2026-11-10 (Dan, chat): CAN address: three firmware builds (A unit 1, A unit 2, B) with address and 1 Mbit/s built in by default; setting a board up by hand over CAN stays possible at any time (C1a + b).
- 2026-11-10 (Dan, chat): Link loss: chosen per channel in the config, default Off, and including a retry mode (C2a). Branch reading of "retry mode": overcurrent reset mode defaults to Count (3 tries) in the custom builds; confirm. (confirmed 2026-11-10: D1)
- 2026-11-10 (Dan, chat): Keep the four small firmware choices for now (C3a: status frame 27, wake-up set, `LINE_UNUSED` = PC13 on board B, analog scaling), guided by the Session 2 pin-map research. (wake-up set replaced by B2; `LINE_UNUSED` on board B is PB2 since B1, B4-a open)
- 2026-11-10 (Dan, chat): Simulation order: compile, then host-side logic tests, then Renode if feasible (C4a). Renode goes in a sandbox on DansPC (WSL).
- 2026-11-10 (Claude, finding): Renode 1.17.0 boots the board A binary on its stock `stm32f4` platform (CAN model present). Missing for a full run: I2C FRAM, MCP9808 and ADC models. (models built 2026-11-11: Renode bench)
- 2026-11-10 (Dan, chat): D1: "retry mode" means both. Overcurrent: retry 3 times before Fault (default in the custom builds). Lost link: outputs follow commands again by themselves when messages return (stock behaviour, shown in `s1_system.py`).
- 2026-11-10 (Dan, chat): D2a: build the full Renode bench, time-boxed.
- 2026-11-10 (Dan, chat): F1: open questions and notes between sessions live in a shared non-repo folder, `C:\projects\_scratch\custom-pdm-shared\` (`SESSION-BOARD.md`), which Dan attaches to the Claude project. `STATE.md` is a shared document: point to it, never copy from it. (shared folder dropped later on 2026-11-10; the STATE.md rule stands)
- 2026-11-10 (Dan, chat): D3a: default link-loss time-out is 1 s, adjustable. (1 s is also the stock firmware default for a CAN input; range 0 to 60 s per input.)
- 2026-11-10 (Dan, chat): D4a: CAN IDs 0x500 / 0x520 / 0x540 are fine for now and must stay user-editable (they are: device parameter over CAN / USB).
- 2026-11-10 (Dan, chat): D5: research options for the PC-side single-PDM layer, or use Dan's existing design (which design: open).
- 2026-11-10 (Dan, chat): The shared non-repo folder / session board idea (F1) is dropped, and so is the "also update the shared document on every state update" rule. `STATE.md` stays the shared document and the one place for open questions and handoffs.
- 2026-11-10 (Dan, chat): Merge everything on `feat/firmware` into `main` (replaces "do not merge" from earlier the same day).
- 2026-11-10 (Dan, chat): D5 closed. Dan has no PC-side layer built as far as he knows; a check of everything on `main` found none (hardware, board scripts and docs only; `reference/` holds the stock KiCad projects). So: research options and bring Dan choices (D5a).

## Orchestration and backup
- 2026-11-10 (Dan, chat): A1a - one orchestrator session now owns both the hardware / enclosure job and the firmware / simulation job. It deploys sub-agents, reviews all their work, keeps state, tracking and memory current, manages PRs, keeps local and remote in sync, and reports everything to Dan in one place. It researches in the repo before asking Dan anything.
- 2026-11-10 (Dan, chat): A5a - re-attach the private GitHub repo `living-relation/custom-pdm` as the remote, as an off-PC backup. Replaces "local-only" (2026-11-09) once the remote is attached.
- 2026-11-10 (Dan, chat): A2a - the docs sweep (iterative-cleaning, report-only) waits until the enclosure questions are answered. (A2a replaced 2026-11-11: run it now) A3a - stale working-memory lines get fixed. A4a - work order: goal 1 fixes and the Renode bench in parallel, open questions to Dan one at a time.
- 2026-11-11 (Dan, chat): B3a - output dimming / pulsing (PWM) stays the stock software method; no hardware-timer PWM, so no IN-pin moves for timers (`docs/firmware-pin-map.md` section 9, Q3).
- 2026-11-11 (Dan, chat): B4-b(b) - add a 10k resistor from PB2 (BOOT1) to GND on board B before ordering, so button (DFU) updates always boot the bootloader. Not built yet.
- 2026-11-11 (Dan, chat): Boards are assembled by JLCPCB or PCBWay, which source the parts; Dan does not buy board parts himself. Part checks must use the assembler's stock (JLCPCB = LCSC parts library; PCBWay = its own sourcing). Parts lookup: Octopart (e.g. https://octopart.com/part/stmicroelectronics/STM32F446RET6).
- 2026-11-11 (Dan, chat): Run repo-cleanup now (a1a), then the docs sweep iterative-cleaning, report-only (a2a; replaces A2a's wait), and re-run the Renode bench with `--build` (a3a: 18 of 18).
- 2026-11-11 (Dan, chat): Cleanup (b1a, b2a): one PR; replaced `DECISIONS.md` lines stay, tagged with what replaced them. Local memory fixes L-a and L-b approved (b4a).
- 2026-11-11 (Dan, chat): b3a - Plan C is closed; Plan B (3 boards on CAN, one enclosure) is final. c1a - apply the docs sweep fixes (`firmware/sim/RESULTS.md`, `docs/firmware-pin-map.md`, enclosure picture re-drawn).
- 2026-11-11 (Dan, chat): r1a - no Renode bug report: the RETTOBASE fix is already on renode-infrastructure master. Keep `firmware/sim/renode` `PdmNvicFix.cs` until a Renode release includes it, then remove it.
- 2026-11-11 (Dan, chat): r2a - delete `firmware/sim/renode/boot_a1.resc` (replaced by the bench) and its `automation.yml` helper entry.
- 2026-11-11 (Dan, chat, standing): questions that only amount to "keep going or not" get the common-sense answer and work moves on; ask only about real problems or real design choices (rule in `AGENTS.md`).
- 2026-11-11 (Claude, default under the rule above): R3 keep the Renode source copy `~/renode-pdm/bench/infra-src` for now. R4 the 0.1 s config save and 620 ms output return are fine; the PC tool must allow a longer save time-out. B4-a board B `LINE_UNUSED` stays PB2 (input, pull-down). B4-c board B wake mask stays 0x0FF until B2 is built.
- 2026-11-11 (Claude, default under the rule above, parts from `docs/parts-audit.md` section 3): C1b Traco TSR 1-2450 as the one 5 V regulator per board (pin clearance over the heat-sink pad checked in the board-fix job; if it fails, C1d). C2b MB85RC64TA FRAM (package width checked against the SOIC-8 footprint first). C4a STM32F446RET6 (look at RET7 only if the heat check shows board air above about 75 C). C6c maker part number field on every part, safety parts first. C7b 120 ohm + solder jumper on each main board (matches 2026-11-08). C5 studs: Blue Sea 2202 / 2201 for BATT and GND. Enclosure H: remove the board A mask window at the next board A rebuild. L1: delete Fusion `board-A-dual` and `LINKED-COPY-unused`.
- 2026-11-11 (Claude, finding): C3 CAN chip needs data-sheet reading before a pick (real check, not a default); enclosure A-G are real design choices for Dan.
- 2026-11-11 (Claude, default under the 2026-11-11 rule, data sheets read): C3d - CAN chip MCP2562FD-E/SN replaces the PCA82C250. Pin 5 = VIO (1.8 to 5.5 V, so 3.3 V logic fits), pin 8 = STBY (high = standby), same as the board wiring and the firmware (`device.cpp`: clear = run, set = CAN off). TJA1051T/3 rejected: its pin 8 is Silent mode, not standby (NXP data sheet Table 3). VDD is still 4.5 to 5.5 V, so P11 (diode drop on the 5 V feed) is checked in the board-fix job.
- 2026-11-11 (Dan, chat): enclosure A (mounting and size) waits until testing is finished and the heat analysis has run. B (material) and C (fan) wait with it, since they depend on the heat result (Claude, default).
- 2026-11-11 (Claude, orchestrator review): board-fix PR #23 accepted. The only DRC rise is 2 lib_footprint_issues warnings on board A ("library not in configuration", same as 55 existing parts); every error category is equal.
- 2026-11-11 (Dan, chat): g1a - merge PR #23 on the passing local state-check (GitHub Actions run stuck in "queued" for over 45 min, no jobs started). p1a - fix P11 with a lower-drop Schottky, Nexperia PMEG2010AEH (290 mV max at 100 mA), in place of D18 (A) / D4 (B); footprint and cold forward voltage checked first, ideal diode (p1b) if it fails.
- 2026-11-11 (Claude, orchestrator review): P11 PR #24 accepted; PMEG2010AEH passes the defined check (thin at -40 C, see `STATE.md` Status).
- 2026-11-11 (Dan, chat, standing): worktrees and feature branches work inside the repo root `C:\projects\active\custom-pdm` (`.claude\worktrees\<job>`), never in `C:\projects\active`. Replaces the `custom-pdm-wt-<job>` folders used on 2026-11-10/11 (all removed). Open questions are re-asked at the end of every reply until answered.
- 2026-11-11 (Dan, chat): s1a - delete the untracked `Claude outputs/` folder (duplicate of the handoff); done.
- 2026-11-11 (Dan, chat): Grok's enclosure TEST 2 pack is the reference for the enclosure direction; do not edit that model. Our version may move connectors to the sides. Screw-terminal studs / ring-terminal points are always horizontal, wherever placed. The rules Dan gave Grok are suggestions, not binding. Pointer: `docs/enclosure-layout.md` section 9.
- 2026-11-11 (Claude, default under the 2026-11-11 rule): the Elmer heat analysis models the TEST 2 style stack (aluminium base-plate sink, fins down, pedestals + insulating gap pad, boards side by side), read from the pack's STEPs without changing them.
- 2026-11-11 (Dan, chat): t1a - "terminals always horizontal" = the ring lug lies flat and the stud points up (as in TEST 2), wherever the terminal sits on the enclosure.
- 2026-11-11 (Dan, chat): u1a - delete the superseded Fusion imports `board-A`, `board-A-dual-k9`, `board-A-inputs`, `board-B` (done; current boards are the `-2026-11-11` folders).
- 2026-11-11 (Claude, orchestrator review): heat analysis branch accepted (energy balance within 0.01 W per run, mesh check +1.2 K on chip spots). It informs enclosure questions A-C; it decides nothing by itself.
- 2026-11-12 (Dan, chat): e1 (enclosure A) - mount flat, lid up (a), or the same unit on a vertical wall; semi-universal mounting if possible, else flat only. Size limit about 14 x 6 x 5 in (356 x 152 x 127 mm, L x W x H); best look = use the length and width, stay as low as possible.
- 2026-11-12 (Dan, chat): X1 and X2 go on one side wall of the enclosure, pointing horizontal (replaces 'both on top' from the Grok TEST 2 brief). Terminal studs / bosses also act as heat sinks. The base may be one machined aluminium part with fins on more than one side.
- 2026-11-12 (Dan, chat): heat targets (85 / 95 / 105 C) are guides, not hard fails: full load is not continuous, and firmware thermal protection can be added (to plan with the firmware work).
- 2026-11-12 (Dan, chat): e2a (enclosure B) - lid is 3D-printed MJF PA12 nylon with heat-set inserts, on the one-piece machined aluminium base.
- 2026-11-12 (Dan, chat): f1a - any enclosure 3D model built before e3-e7 are answered (e.g. the low-profile draft on `feat/enclosure-lowpro`) is a rough draft only; it is redone once e3-e7 are answered.
- 2026-11-12 (Dan, chat): f2a - remove the superseded handoffs (`.claude/handoff/HANDOFF-2026-11-11*.md`) and fix out-of-date `STATE.md` lines in one small PR after the enclosure draft PR.
- 2026-11-12 (Dan, chat): e3c (enclosure C) - fans fitted, pushing air in. Pick the quietest fans possible; one larger fan is preferred if it lowers noise. Fans switch on from a temperature trigger whose limit is adjustable in software (firmware item).
- 2026-11-12 (Dan, chat): h1a - keep the stopped helper's leftovers (`feat/enclosure-lowpro` worktree and branch, WSL `~/scratch/encl-lowpro/`) until e3-e7 are answered; reuse its measuring scripts for the 3D build.
- 2026-11-12 (Dan, chat): e4a (enclosure D) - the 150 A feed (and GND) reaches the three boards' M6 terminals by flat copper bars from the studs, slotted holes for tolerance.
- 2026-11-12 (Dan, chat, standing): enclosure size and appearance are the main goal; cooling adapts to them (not the other way round).
- 2026-11-12 (Dan, chat): j1a - board A's DT15 headers are not used as outside connectors (they are sealed bulkhead parts not doing that job here). X1 (HD30) and X2 (HDP24) stay as the box connectors, on one side wall, pointing horizontal.
- 2026-11-12 (Dan, chat): e6a (enclosure F) - remove the DT15-12PA (J3) from both board A's; its wires (8 outputs, IN1, IN2) are soldered straight to board A and run to X1 / X2. No plugs between boards inside the box (Dan: nothing inside ever needs to be disconnected). Board A change, to do. This removes the DT15 height, so the enclosure gets lower.
- 2026-11-12 (Dan, chat; 'much easier to stack the boards'): e5a (enclosure E) - each input board sits on standoffs above its own main board.
- 2026-11-12 (Claude, default under the 2026-11-11 rule; Dan may override): k1a - a cable-tie point built into the base near the board A solder joints holds the board A to X1 / X2 wire bundles (vibration). No tie-down between boards (Dan).
- 2026-11-12 (Dan, chat): n1b - each input board plugs straight onto its main board with a board-to-board stacking header (e.g. 2.54 mm pin header + socket); fallback n1a = keep the short JST GH cable. Board change on all boards (connector spots must line up), to do.
- 2026-11-12 (Dan, chat): p1a - board B J6 (Micro-Fit 2x2: CAN + 2 inputs) is removed; its wires are soldered straight to board B (same as e6a).
- 2026-11-12 (Dan, chat): p2a - board B OUT1-4 reach their enclosure studs by short copper straps on the REDCUBE M4 terminals (no thick wires); the studs also shed heat.
- 2026-11-12 (Dan, chat): e7b (enclosure G) - board A is held on the heat sink by its 4 corner M3 screws plus a compliant gap pad; no centre hole or lid post (small boards bend little).
- 2026-11-12 (Dan, chat): the planned layout sketch is the target: A1, A2, B in a row; input boards stacked on each via stacking headers; BATT / GND copper bars across to their studs; board B OUT1-4 straps to studs; soldered wires to X1 / X2 on the front wall. Header spots, stud and wall positions still TBD.
- 2026-11-12 (Dan, chat): q1a - board changes first (DT15 off board A, J6 off board B, stacking headers on all boards), then the 3D enclosure around the real boards.
- 2026-11-12 (Dan, chat): r1a - stacking header in the centre of each main board (old DT15 / J6 spot); input boards move to the main boards' 4-hole M3 pattern (H1-H4, same on A and B) so one input board design fits both and the screws go through the stack; X1 / X2 wire solder pads on the main board edge facing the front wall.
- 2026-11-12 (Claude, finding from the board-stack height study): stacked input boards on the H1-H4 pattern clash with the M6 feed terminals (A and B) and with board B T1-T4 in its centre; board A J3 pins 1-2 carry CAN_L / CAN_H (so board A needs CAN wire pads too).
- 2026-11-12 (Dan, chat): z1a - keep the three boards as separate nodes on one CAN bus (stock dingoFW, tested); they are made to look like one PDM in the PC / ECU software (D5a), not by a hardware gateway.
- 2026-11-12 (Dan, chat): x1a - input boards keep the existing JST GH 12 cable to their main board (board A J6, board B J7, input board J1); replaces n1b (no stacking headers, r1a header placement dropped). Input boards need no board change.
- 2026-11-12 (Dan, chat): x2c - input board mounting is decided in the 3D model, preferring under the nylon lid (x2a).
- 2026-11-12 (Dan, chat): v2b - board B OUT5-8 keep their REDCUBE M4 screw terminals (wires to X1); swap to solder pads only if they become a problem. Copper bars and straps may be thin (sized for current in the 3D work).
- 2026-11-12 (Dan, chat, standing): board naming - 'top' and 'bottom' mean only the two board SURFACES in the normal mounting position (top = component side, facing the lid; bottom = heat-sink side). Edges are never 'top' / 'bottom'. Main board edges (A and B, same KiCad frame): front edge = PCB -Y edge, facing the enclosure front wall (X1 / X2); back edge = PCB +Y; left end = PCB -X (M6 feed terminals); right end = PCB +X (board B extension, T5-T8).
- 2026-11-12 (Dan, chat): b1b - copper bars and straps sized for the full 150 A feed, or as close as the layout allows.
- 2026-11-12 (Dan, chat): a1a - board A wire pads (OUT1-8, IN1, IN2, CAN_L, CAN_H) use the 12 DT15 through-holes where they are; no copper change.
- 2026-11-12 (Dan, chat): a2a - board B wire pads (CAN_L, CAN_H, IN1, IN2) move from the J6 spot to the board B front edge, clear of T1-T8, the M6 terminals and the strap / wrench area. Replaced by a2b.
- 2026-11-12 (Dan, chat): y1a - one sealed USB-C bulkhead (jam nut) on the front wall feeds a small bus-powered USB hub inside, with a short USB cable to each board. Check at hub part pick that the boards do not back-feed 5 V into VBUS.
- 2026-11-12 (Dan, chat): a2b - board B wire pads stay in J6's 4 holes in the board centre (pads-only footprint, no re-route, same as a1a). The wires lie flat on the top surface under the raised T1-T4 straps, so they do not block the straps or the wrench; check the REDCUBE terminal height leaves room for them.
- 2026-11-12 (Claude, orchestrator review): wire-pads PR #41 accepted (checks equal to main, same holes, no copper change).
- 2026-11-12 (Dan, chat, after reviewing enclosure v1 / PR #42): v1 rejected (Grok's TEST 2 looked better). Direction for v2: start from a COPY of Grok's TEST 2 model (the pack itself stays untouched) and change it as little as possible; our DECISIONS.md board / wiring decisions win where they conflict (list each conflict). Model in Fusion (Fusion lock), using real vendor CAD models for X1, X2, the USB-C bulkhead, studs / bosses and fans so cut-outs, nut space and flange clearance are right.
- 2026-11-12 (Dan, chat): v2 - all copper bars and straps are inside the enclosure; only the TOP of each power terminal shows. Terminals are large female-threaded hex bosses (like board B's REDCUBE, much bigger), stud points up (t1a). Fans mount on the heat sink (as in TEST 2). The lid-to-base fastening is modelled and shown.
- 2026-11-12 (Dan, chat): v2 - X1 and X2 mount on a step-down in the lid (as in TEST 2), turned to point horizontally toward one side of the PDM; the step gives a flat mounting face and breaks up the box shape. Replaces 'X1 / X2 on the front wall' (j1a placement only).
- 2026-11-12 (Dan, chat): v2 - research popular professional PDM / PDU makers (motorsport and automotive) and use their design cues so the whole unit looks professional. Enclosure v1 questions i1-i4 are dropped.
- 2026-11-12 (Dan, chat): v2 concept (draft PR #44) rejected - it looked like Grok's model chopped up and rearranged. Target look = Grok TEST 2 variant b as rendered in the updated pack (C:\Users\danie\_staging\custom-pdm-enclosure-handoff\custom-pdm-enclosure-handoff.zip, HANDOFF.md 'What correct looks like'; old pack kept beside it as -v1), with more reinforced-looking feet and a deeper overall housing so the connectors fit on the FRONT long side. Replaces the 'X1 / X2 on a lid step-down pointing to one side' line.
- 2026-11-12 (Dan, chat): h2a - keep round X1 (HD30) and X2 (HDP24) on the front long side; no rectangular Link-style connector. Use ACCURATE CAD models from any source (TE after v4a, or other vendor / distributor / community models), never home-made placeholders. v4a - accept TE's ECAD model terms and download; also search other sources (TraceParts, 3D ContentCentral, GrabCAD, SnapEDA / Ultra Librarian, distributors).
- 2026-11-12 (Dan, chat): v2 (input board #2 vs connector housing) - not known until real models are placed; check with the real CAD. v1 (connector direction vs fan end) - Dan: doesn't matter.
- 2026-11-12 (Dan, chat): v3b - power terminal bosses are custom copper hex bosses, female-threaded, machinable in-house on a 3-axis mill.
- 2026-11-12 (Dan, chat): v5 - two fan options to model: (1) Grok's 2 x 30 mm fans, embedded inside the heat-sink envelope (nothing sticking out past the enclosure outline); (2) one Noctua fan blowing UP into the heat sink, sunk into a machined pocket in the fins with an air gap between the fan and the mounting surface, optionally with swept fin channels for an outward / radial airflow vortex. Replaces 'one larger fan pushing along the fins' (e3c detail); fans stay quiet and temperature-triggered.
- 2026-11-12 (Dan, chat): b1a (X1 / X2 sticking out 21 mm, 61 mm with plugs, is fine), b2a (fan option F1 = two 30 mm fans inside the heat-sink envelope goes forward; F2 kept as the alternative), b3a (gap pad k >= 3 W/mK), b4a (no OUT1-4 straps; copper bosses sit on board B T1-T4; replaces p2a). OUT1-4 bay needs a wire-way through the lid to its edge (ring lugs could not reach the deep bay).
- 2026-11-13 (Dan, chat): c1b + d1a - OUT1-4 lugs sit on copper offset risers held in one solid G10 carrier block (thick walls between lug seats, no thin ribs); the carrier takes wrench torque (keyed risers, bolted to the heat-sink posts at board B H2 / H4). All parts 3-axis-millable in-house.
- 2026-11-13 (Dan, chat): e1a - upper OUT lug row raised 4 mm and the carrier widened so bare-metal gaps are >= 4 mm and carrier walls >= 3 mm; the wire-way between the BATT / GND collars stays as is. Standing: insulated wire may touch plastic; only bare metal needs clearance.
- 2026-11-13 (Dan, chat): F2 fins are smooth continuous sweeps (CNC-friendly), with a 3D-printed parabolic flow cone under the fan.
- 2026-11-13 (Claude, orchestrator review): enclosure v2b PR #46 accepted (interference check clean F1 / F2, bare-metal clearances >= 5.2 mm, Würth 74650074R 1.2 N·m respected via the carrier).
- 2026-11-13 (Dan, chat): F2 flow cone = reverse velocity-stack flare (concave, point at the fan hub, tangent blend into the plate), PA12 MJF, countersunk M3 from the plate top into a heat-set insert; replaces the convex paraboloid. g1a - clean up finished worktrees, branches, scratch and stale docs.
- 2026-11-13 (Dan, chat): r2a - change the MCU to STM32F446RET7 (105 C grade, same footprint) on boards A and B; fallback r2b (keep RET6 and shed loads earlier) if the RET7 does not work out (availability / assembler stock). Replaces C4a's 'RET6, look at RET7 if > 75 C'.
- 2026-11-13 (Dan, chat): r3c - the two Sunon 30 mm fans run whenever the PDM is awake (no temperature-switched fan output); replaces the e3c 'temperature-triggered fan' detail. r4c - no fan-fail detection (2-wire fans kept).
- 2026-11-13 (Dan, chat): r5a - thermal protection = config-based load shedding by priority plus a small firmware change: warn / critical limits become config settings, critical recovers by itself after cooling with hysteresis (no power cycle), STM32 die temperature sent on CAN. Plan: docs/firmware-thermal-plan.md. r6c - starting limits are set after bench measurements (thermocouples).
- 2026-11-13 (Dan, chat): h1b - retire the 2D enclosure-layout generator (tools/gen_enclosure_layout.py) and its automation.yml entry; docs/diagrams/enclosure-layout.svg stays as a static, superseded picture.
- 2026-11-13 (Dan, chat): r7a - the two fans are powered from one PDM output set to always-on in config (no extra power source into the PDM); that output is wired inside the box to the fans and its X1 cavity becomes a spare. Which output: the 7.5 A board A output nearest the fan end, picked in the firmware-thermal / enclosure job.
