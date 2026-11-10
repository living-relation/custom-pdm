# STATE - custom-pdm

Updated 2026-11-10. Decisions live in `DECISIONS.md`; scripts are listed in `automation.yml`.

**Last cleanup:** 2026-11-08 @ 46e5a49 (repo-cleanup PR)
**Kept branches:** none (feat/board-b merged locally 2026-11-10)
**Hook:** state-check workflow installed, comment mode (2026-11-08)

## HANDOFF - START HERE (written 2026-11-10 by claude-cloud-dc, for the next session)

**Do this now.** You are the orchestrator. Dan (2026-11-10): run the three jobs below with parallel agents, then review their work. Do not do the jobs yourself.

1. Re-check the tip: `git status -sb` and `git log --oneline -1` in `C:\projects\active\custom-pdm`. Expected: `main`, clean, no remote. The commit that added this section is the tip (its parent is `5844e83`).
2. Read `AGENTS.md`, this file, `DECISIONS.md`, and the working memory `%USERPROFILE%\.claude\working-memory\custom-pdm\INDEX.md`.
3. Start one agent per job, each in its own git worktree and branch (the board B build rewrites `hardware/board-b-max` in whatever tree it runs in).
4. Review each result, then merge into `main` locally, one at a time (`git merge --ff-only` or `--no-ff`). No push, no PR: the repo is local-only.
5. Remove this section when the three jobs are merged, and update Status below.

**Do not:** push or re-attach GitHub; start or stop workstation workers; run two agents in Fusion at once (one Fusion lock, see `C:\projects\active\workstation\agents\projects-AGENTS.md` section 5); make big design decisions without asking Dan; commit memory files; treat `docs/diagrams/` as a source of truth.

### Job A - enclosure and heat sink layout (branch `feat/enclosure`)
- Goal: a first enclosure layout proposal that Dan can approve or change. Start in 2D (board positions, wall items, heat path) before any 3D.
- Inputs: boards A1, A2 = 72.4 x 95.3 mm; board B = 111.4 x 95.3 mm; three input boards 66 x 64 mm (they can stack over a main board on standoffs). Wall: X1 HD34-24-21SN, X2 HDP24-24-47SE-L017, six studs (BATT 150 A, GND, board B OUT1-4 at 31 A with rubber boots). Wiring: `docs/box-connectors.md`, pictures in `docs/diagrams/`.
- Heat: switches are on top; the bare back side carries +12 V, so it needs an insulating gap pad to the heat sink. Board A: pedestals under U8/U11 and U10/U13, a pocket for J3's pins, a centre standoff. Board B: bottom mask openings under every switch (four BTS70012 near the centre, four BTS7004 in the right column). Dan: "we'll build in more than enough cooling capacity". Material so far: aluminium or MJF with a heat sink.
- Only this job may use Fusion. Fusion work never needs asking (Dan), but hold the lock.
- Open, ask Dan: mounting position in the car, size limits, lid and sealing, fan or no fan, how the 150 A feed is split to three boards (busbar).

### Job B - firmware pin map (branch `feat/fw-pin-map`)
- Goal: `docs/firmware-pin-map.md`, one table per board (A, B): every MCU pin the firmware must know (outputs IN / DEN or DSEL / current sense with ADC channel, inputs, CAN, I2C, LEDs), and what differs from stock dingoFW. No firmware code yet.
- Source of truth: the schematics. Export a netlist with kicad-cli and read it with `tools/netlist_pins.py`. Board A: outputs 1-2 are a dual pair (DSEL on the old PF_DEN2 pin), inputs IN_3..IN_7 on PC10, PC11, PB4, PC13, PB3. Board B: see its Status entry below (IN5-8, DEN5_6, DEN7_8, IS5-8, B_IN3-10, B_AN).
- Check each new pin's timer / ADC function against the STM32F446RE datasheet (cite it). PWM timers for the new IN pins were picked from memory and are UNCONFIRMED: PA8 TIM1_CH1, PB10 TIM2_CH3, PA15 TIM2_CH1, PC8 TIM8_CH3.
- Read-only on `hardware/`.

### Job C - tidy board B (branch `feat/board-b-tidy`)
- Goal: clear the cosmetic leftovers without changing anything electrical.
  - Overlapping silkscreen reference texts (DRC `silk_overlap`, `silk_over_copper`), mostly in the four copied channel blocks and at T1-T4.
  - One dangling 1 mm stub on PF_IN8 near (47.4, 42.4): the pruning in `tools/route_board_b.py` runs before the plane repair; run it again after.
  - New parts lack the Digi-Key / LCSC fields the schematic symbols have (47 parity field mismatches).
- Work only in `tools/*board_b*` scripts, never by hand in the board file: `tools/build_board_b.ps1` regenerates everything from baseline `fe19c28` (about 10 minutes; start it with `Start-Process` and poll its log, Remote Desktop Commander calls return after about 5 s).
- Pass condition: `python tools/drc_diff.py %TEMP%\board-b-build\drc_base.json %TEMP%\board-b-build\drc.json` shows 0 unconnected and unchanged clearance (7), hole_clearance (56), track_width (101), annular_width (20). Make `drc_base.json` from `reference\dingoPDM-Max\dingoPDM-Max\dingoPDM-Max.kicad_pcb`. `tools/check_board_b.py` must print ALL OK. The PCB must stay KiCad 9 format (`(version 20241229)`).
- Only this job touches `hardware/board-b-max` and the board B scripts.

### Review checklist for the orchestrator
- Each job stayed in its own files; `git diff --stat main...<branch>` shows nothing unexpected (the board A build rewrites `hardware/board-a`: restore with `git checkout HEAD -- hardware/board-a` if it shows up).
- Job C: rerun the build yourself and compare the DRC table; re-import to Fusion only if copper changed.
- Job B: spot-check five pins against the netlist.
- Job A: every assumption is listed as a question for Dan, none decided silently.
- Update `STATE.md` and `DECISIONS.md`, then report to Dan in his format (TL;DR, bullets, lettered questions).

### Decisions already made (do not re-ask)
- All in `DECISIONS.md`. The ones that bite here: local-only repo; one pin per output on enclosure connectors, no ganged pins; power sources get socket contacts on the box side; X3 dropped; board B = one board; outputs leave board B on REDCUBE terminals; per-pin maker rating is the current criterion; at a finishing point keep going, stop only for something Dan must answer.

### Leftovers (each needs Dan's keep / remove call; none are in the way)
- Fusion project `custom-pdm`: `board-A-dual` (broken import, no nets) and `LINKED-COPY-unused`.
- `%LOCALAPPDATA%\Workstation\claude-fusion\`: helper scripts (`call.ps1`, `up*.py`, `chk*.py`, `*.ulp`, `kicad\`), TE drawings in `te-drawings\`.
- `%TEMP%\board-b-build\` build outputs; `.github/` workflow files that no longer run; the private GitHub repo `living-relation/custom-pdm` (stale since 2026-11-09, detached on purpose).

### Mistakes not to repeat
- Committed staged baseline files by accident (1b16fdf): check `git diff --cached --stat` before every commit.
- Told Dan "+35 mm" for board B before laying it out; it became +39 mm. Give sizes only from a placed layout.
- Chose the 85 A terminal before checking it fits; it did not. Check footprints against the board first.
- Stated a pin shortage from a routing-only view, which reopened a decision (D1b to F1a). Count pins from the schematic.
- KiCad 9 python: `BOARD.Remove()` corrupts item lists; a python-made `NETINFO_ITEM` needs `thisown = False`; loading a second board makes the first crash on Save.
- Left debug files in the board folder and committed them; they are git-ignored now.

## Status
- Repo is local-only on DansPC (2026-11-09): detached from GitHub (`living-relation/custom-pdm` is now private; kept detached for now, Dan 2026-11-09). PR history saved in `docs/github-pr-history.md`. The GitHub state-check workflow no longer runs. Board B (dingoPDM-Max based) lives in `hardware/board-b-max/`.
- Repo created (was public on GitHub). Board A design source is KiCad (`hardware/board-a/`). Rebuild it with `tools/build_board_a.ps1` (baseline + scripts, then ERC/DRC). The PCB must stay KiCad 9 format (KiCad 9.0.8 python edits it): Fusion's importer loses all nets from a KiCad 10 PCB. Schematics are KiCad 10 format upstream and import fine. kicad-cli 10 is used read-only. Fusion is for viewing, 3D and later checks (re-import after each round).
- Reference KiCad sources (dingoPDM v7.5, dingoPDM-Max) cloned locally under `reference/` (git-ignored, about 350 MB).
- dingoPDM v7.5 imported into Fusion Electronics (Fusion project `custom-pdm`, Sheets translation): design, schematic and board files created. Check: 115/115 named nets match; all 156 parts. Board checked: outline 72.39 x 95.25 mm, 4 copper layers, 522 pads, board image looks right.
- Part and net lists from the import are in the models folder (`Desktop\models\custom-pdm-import-check`, OneDrive, add-only).
- BOM v4 is in `docs/custom-pdm-bom-v4.xlsx` (prices are estimates, many yellow guesses).
- Board A step 1 done (PR #2): U8+U9 (2x BTS7002) replaced by one BTS7008-2EPA dual at U8. J3 re-pinned: pin 7 = OUT2, pin 8 = OUT1 (was IN1), pin 12 = IN1 (was OUT2). PF_DEN2 MCU pin is now PF_DSEL1_2. PF_IS2 ADC path is spare (buffer input tied to GND). DRC/parity: 0 unconnected, no shorts, all other findings same as the unmodified dingoPDM baseline (28 clearance findings pre-exist).
- Fusion `custom-pdm` project: root = clean import of the original; `board-A` = unmodified re-import (+ `LINKED-COPY-unused`, deletable); `board-A-dual-k9` = modified board A (143 parts, 111 nets = KiCad); `board-A-dual` = broken KiCad 10 import with no nets (deletable).
- Board A inputs DONE (PR #7, 2026-11-09), part of the default build. Fusion re-import `board-A-inputs` checked: 135/135 parts, all nets match by pin set (J1/J2/J5 multi-pad pins only renamed).
  - J6 (JST GH 12-pin, side entry) at the left edge: 1-5 IN_3..IN_7 = PC10, PC11, PB4, PC13, PB3 (ex-SWO); 6-8 NC; 9 PC2 spare analog (R12 DNP); 10 +3V3; 11-12 GND.
  - All test points removed (THT ones that joined layers got a via; dead-end stubs removed). SWO dropped. GND fenced-in pad C32.1 got a stitching via; one floating GND sliver covered by a no-fill area.
  - DRC: 0 unconnected, 0 shorts, same 28 inherited clearance findings as stock dingo. DRT logo G1 removed (Dan), so no new silkscreen notes. ERC 623 (was 632).
  - Board B (Max) check: ~9 new inputs escape without rework (PC10, PC11, PC13, PB3 + PB12, PB10, PB1, PC4, PB4). Plan ~9 there (Dan, A6a). System: 7 + 7 + ~11 = ~25 inputs.
  - Input board (DIP pulls, DT panel connector) not started.
- Plan B (3 boards on CAN, one enclosure) leads; Plan C (one brain + power slices) still open.

- Input board (`hardware/input-board/`, branch `feat/input-board-pcb`): generated by `tools/build_input_board.ps1` (schematic text -> netlist -> KiCad 9 PCB: place, route, pour). 2-layer, 66 x 64 mm. 8 digital channels + 1 analog (0-5 V divider 10k/20k). Per channel 4.7k + BAT54S + 10 nF; 10k pull-up (SW1) / pull-down (SW2) on the wire side, Omron A6S-8104 DIPs. J2 Molex Micro-Fit 2x6 (wires: 1-8 IN, 9 analog, 10-12 GND), J1 JST GH 12 (to board A J6). ERC/DRC clean (0 unconnected, 0 parity issues). Fusion import `input-board` checked: 50/50 parts, 36/36 nets match (PR #8).

- Board B (`hardware/board-b-max/`, branch `feat/board-b`): schematic done, rebuilt by `tools/build_board_b.ps1` (baseline fe19c28 -> `tools/sch_board_b.py` -> netlist check -> ERC).
  - Added 4 x BTS7004-1EPP channels (U23-U26, sheet `BTS7004_1EPP` copied from dingoPDM MIT, RSENSE 1.2k) on page `HighCurrentDrivers2`, plus a second LM324 sense buffer (U22).
  - MCU pins: IN5-8 = PA8, PB10, PA15, PC8; DEN5_6 = PB12; DEN7_8 = PB15; IS5-8 = PA2, PA4, PA7, PC4.
  - Inputs B_IN3-10 = PC14, PC15, PB2, PD2, PB4, PB5, PC10, PC11; B_AN = PB1. PC13 is spare.
  - Connectors: T1-T8 bolt-down terminals, one per output, all Wuerth REDCUBE 74650074R (M4, 7 x 7 mm, 50 A at 20 C; the 85 A 74650094R is 10 x 10 mm and does not fit between a BTS70012 and its output diode). Deutsch DT header J4 removed. J6 Molex Micro-Fit 2x2 = 1 CAN_L, 2 CAN_H, 3 INPUT2, 4 INPUT1 (order follows the old J4 track ends). J7 JST GH 12 top entry (BM12B) to input board #3 (same pinout as board A J6).
  - Test points removed. Stock 4 x BTS70012 (OUT1-4) unchanged.
  - Netlist check passes. ERC: the only new errors are the same types the stock channels already have (paralleled OUT pins, GND network).
  - PCB DONE 2026-11-10 (`tools/pcb_board_b.py` then `tools/route_board_b.py`, both run by the build, about 10 min): board grows 39 mm to the right (72.4 -> 111.4 x 95.3 mm). Old area: T1-T4 on the four output pours, J6 where J4's centre pins were. New column: four 15 A channels whose placement and copper are copied from dingoPDM v7.5's BTS700x-1EPP block (board A baseline, MIT), turned 90 degrees, each with its terminal and output pour; bottom layer there is +12 V. A 7.5 mm strip between old edge and blocks holds J7, U22 (LM324) and R52-R55/C46. Two extra mounting holes H5/H6 (board only).
  - Routing: all 27 new nets routed (17 MCU pins fanned out with a stub + via each, tightest first; each net routed from its via). Unused fan-out vias and leftover stubs pruned; GND / +3V3 pieces cut off by new tracks re-joined.
  - DRC vs the stock Max (`tools/drc_diff.py`): 0 unconnected; clearance 7 = 7, hole clearance 56 = 56, track width 101 = 101, annular 20 = 20 (all inherited). New: 6 courtyard overlaps (terminals T1-T4 beside each other and beside the BTS70012s: bodies are 7 x 7 mm and clear), 1 dangling 1 mm stub on PF_IN8, silkscreen overlaps (cosmetic), 47 footprint field mismatches in parity (new parts lack Digi-Key/LCSC fields).
  - Fusion: imported as `board-B` in project `custom-pdm`; 200/200 parts, 137/137 nets match (10 nets differ only in how repeated pad numbers are named: T1-T8, J1, J3).
  - Render: `docs/diagrams/board-b-top-render.png`.
  - Open on board B: silkscreen tidy (overlapping reference texts), fields for the new parts, the PF_IN8 stub, a human look at the layout before ordering.

## Open items
- Box connectors (Dan): X1 HD30 24-21 = all connector outputs (16 x 7.5 A from A1/A2 + board B OUT5-8 on size 12 cavities B, D, E, G); X2 HDP 24-47 = signals; studs = BATT, GND, board B OUT1-4. X3 dropped. Wire list in `docs/box-connectors.md`. To buy: size 20 contacts, sealing plugs, 6 studs with boots. X1 current check done: every pin is at about 60% of its TE rating; TE publishes no total-connector limit (Dan: per-pin rating is enough). Illustrations (not a source of truth): `docs/diagrams/*.svg`, drawn by `tools/gen_connector_maps.py`.
- Heat sink design: two pedestals (U8/U11 and U10/U13), insulating gap pad, pocket for J3 pins, center standoff.
- Harness: J3 pinout changed on board A (see Status).
- Firmware (later): outputs 1-2 are now a dual pair (DSEL on the old PF_DEN2 pin).
- Review the 28 pre-existing DRC clearance findings before ordering.
- Decide 256 Kbit FRAM vs 64 Kbit substitute.
- Design the 150 A feed busbar.
- Pick connector part numbers.
- Pick fab: JLCPCB vs PCBWay.
