# STATE - custom-pdm

> **Shared document: every agent and session reads and writes this file (Dan, 2026-11-10).**
> - This is the one place for progress, open items, open questions and handoffs. It is how sessions talk to each other.
> - Keep each session's open questions in its own section. Do not edit or answer another session's section; leave a note in your own.
> - Do not copy or repeat anything from this file in any other file (docs, results, memory, handoffs). Point to it instead: `STATE.md`, section name.

Updated 2026-11-10. Decisions live in `DECISIONS.md`; scripts are listed in `automation.yml`.

**Last cleanup:** 2026-11-08 @ 46e5a49 (repo-cleanup PR)
**Kept branches:** none (feat/firmware merged locally 2026-11-10)
**Hook:** state-check workflow installed, comment mode (2026-11-08)

## HANDOFF - START HERE (firmware / simulation job, updated 2026-11-10 after the merge)

**Owner (from 2026-11-10, Dan A1a):** the orchestrator session in "Orchestrator session 3" below and the sub-agents it deploys. Other sessions: do not touch `firmware/`.

**Do this now**
1. Check the tip first: `git log --oneline -3` on `main` must show "Merge feat/firmware" (2026-11-10) at or near the top, and `git status` must be clean. If not, stop and ask Dan.
2. Next steps, in this order unless Dan says otherwise: (a) the Renode bench (Dan, D2a), time-boxed; (b) research options for the PC-side single-PDM layer and bring Dan choices (D5a). Nothing for that layer exists in the repo yet: the only code is the test stand-in in `firmware/sim/s1_system.py` (`set_output`, `can_input`, `Status`). For (a): Recipe: the "Next task, firmware session" bullet under "Next" below. Work on a new feature branch, then merge locally (repo rule in `AGENTS.md`).

**Do not**
- Do not push anything upstream to dingoPDM / dingoFW. No PRs: the repo is local-only.
- Do not flash anything. No hardware exists yet.
- Do not build firmware from `/mnt/c` (CRLF checkout): use `firmware/sim/renode/build_wsl.sh`, which builds from `git archive` (it names a branch: pass / edit it to `main`).
- Do not answer or edit the orchestrator session's questions (B1-B4, enclosure A-H).

**State**
- Everything from branch `feat/firmware` is merged into `main` (Dan, 2026-11-10) and the branch is deleted. One working tree on `main`. No remotes, no stashes, no other worktrees.
- Answered decisions: `DECISIONS.md`, section "Firmware and coordination".
- Results, limits, and the firmware choices made: `firmware/sim/RESULTS.md`.

**Checks (run before any commit that touches `firmware/`)**
- WSL: `bash firmware/sim/renode/build_wsl.sh` (strip CR first): 4 builds OK, the only warning is the linker "RWX segment" one.
- Linux / WSL: `firmware/sim/build.sh custompdm_a <out> 1`, same for `custompdm_a <out> 2` and `custompdm_b <out> 1`, then `python3 firmware/sim/s0_board_audit.py <out>` (expect 36 of 36) and `python3 firmware/sim/s1_system.py <out>` (expect 26 of 26).
- Board folders are generated: change `firmware/tools_custom/port_boards.py`, re-run it, never hand-edit `firmware/boards/custompdm_*`.
- `git diff --cached --stat` before every commit (repo rule).

**Open decisions:** none from this session. Session closed 2026-11-10.

**Leftovers of this job (each needs Dan's keep / remove call)**
- WSL `~/renode-pdm` (2.0 GB; `dl/` holds 330 MB of downloaded archives that can go).
- `firmware/ChibiOS` (git-ignored local clone, needed to build).
- `%TEMP%\custom-pdm-fw-import\` (two import tarballs and helper scripts; the scripts that matter are already in `firmware/sim/renode/`).
- `firmware/.gitmodules` (from upstream; inert here).
- The zip sent in chat on 2026-11-10 (`custom-pdm-firmware-sim-2026-11-10.zip`) predates the C1 / C2 / D3 changes: the repo is the source of truth.
- Lines added to working memory `INDEX.md` on 2026-11-10 (sandbox gotchas).

**Mistakes not to repeat (this job)**
- Ran `sim/build.sh` with the unit number where the output folder goes: it created `firmware/1` and `firmware/2` full of build output, and they were committed once. List what is staged before committing.
- `device_commit_files` delivered an older copy of a tarball that had just been rebuilt. Check contents after extracting.
- PowerShell `$ErrorActionPreference = 'Stop'` plus a git warning on stderr stopped a multi-step command half way. Do not combine them; send git stderr to `$null`.
- Wrote a test that assumed the stock overcurrent default was "3 tries"; it is None. Read defaults from `core/param_defs.h`.
- First measured the power-up ON pulse as 4 ms because every test case had the same message timing. Vary the timing before quoting a number.
- Proposed new "front door" firmware before reading upstream; upstream already had most of it. Read the code first.
- Put this session's questions into the orchestrator's "Waiting on Dan" line. Keep them in this session's own section.

## Orchestrator session 3 (Claude-Session 014aA8s6rstT9Sxtn4fsxsmM, started 2026-11-10)
Owns both earlier jobs (Dan A1a, `DECISIONS.md` "Orchestration and backup"). Dan's goals: (1) finish the boards, parts and firmware; (2) full Renode bench with passing tests; (3) enclosure with heat sink (handbuilt-cad tools + Fusion).
- Remote: attached 2026-11-10 (Dan ran the commands; agents are blocked from adding or changing a remote). `origin` = private GitHub repo, `main` level with local at d319ad3. Rules: `AGENTS.md`. This replaces every "local-only / no PRs" remark further down this file.
- Jobs in flight (each in its own worktree `C:\projects\active\custom-pdm-wt-<job>`, sub-agents do not edit `STATE.md` / `DECISIONS.md`, the orchestrator reviews and merges):
  - `feat/board-b-in5-pc13` (wt `-bin5`): B1 move of B_IN5 from PB2 to PC13 on board B, hardware plus the firmware pin and `LINE_UNUSED`. Status: started 2026-11-10.
  - `feat/renode-bench` (wt `-renode`): the Renode bench from "Next" below. Only touches `firmware/sim/renode/`. Status: started 2026-11-10.
  - `feat/parts-audit` (wt `-parts`): every part on the three boards checked against BOM v4, datasheets and stock; options for the open part choices. Status: started 2026-11-10.
- Open questions for Dan from this session: none yet. Inherited and not asked yet: B3, B4, enclosure A-H, L1 (see the section below).

## Next (updated 2026-11-10)

- **Next task, firmware session (Dan D2a, 2026-11-10): build the full Renode bench, time-boxed.** Start point: `firmware/sim/renode/boot_a1.resc` boots the board A binary to the idle thread on Renode's `platforms/cpus/stm32f4.repl`. To add: (1) an I2C FRAM at 0x50 on `i2c1` (MB85RC256V: 2 address bytes, then data) so config load / save works; (2) MCP9808 at 0x18 on `i2c1` (check `renode/` for a ready model first); (3) an ADC1 model at 0x40012000 feeding the DMA2 stream the firmware uses, or a simpler stand-in, plus the PROFET sense model from `firmware/sim/pdmsim.py`; (4) a second and third machine on one CAN hub and a Robot test that repeats `s1_system.py` checks. Stop and report if any one of these takes more than a session. Sandbox: `~/renode-pdm` in WSL; rebuild binaries with `firmware/sim/renode/build_wsl.sh`.
- **Firmware is in `firmware/` on `main` (merged 2026-11-10, Dan).** `firmware/` = upstream dingoFW `d594cd7` (MIT) plus boards `custompdm_a` / `custompdm_b`; ChibiOS is a git-ignored local clone in `firmware/ChibiOS` (corygrant/ChibiOS @ 879cf757). Results and open choices: `firmware/sim/RESULTS.md`.
- Renode sandbox on DansPC: WSL Ubuntu, `~/renode-pdm` (Renode 1.17.0 portable, xPack arm-none-eabi-gcc 14.2.1, Python venv with Robot Framework 6.1). User-level only; remove with `rm -rf ~/renode-pdm`. Scripts: `firmware/sim/renode/`.
- Jobs A, B, C from the 2026-11-10 handoff are merged (details in Status). Nothing is mid-flight; no open branches or worktrees.
- **Waiting on Dan (orchestrator session):** see "Open questions: orchestrator session" below. Do not start 3D enclosure work before he answers the enclosure questions.
- Open, small: leftover board A mask window at the old U9 spot (x -12.9..-8.94, y 11.38..14.02); the pin map still lists `LINE_SWO` for removal on board A although board B keeps it, and board A HSE crystal is by net name only; 5 schematic-parity findings on board B (stock Max 0 on this check); courtyards_overlap 10 (stock 4) and lib_footprint_issues 199 (stock 140) from the new parts.
- Fusion lock is free (last release 2026-11-10 19:23). Do not run two agents in Fusion at once.
- Docs changed since the last cleanup (2026-11-08): run iterative-cleaning (report-only) after Dan answers the questions (A2-b).

### Open questions: orchestrator session (Claude-Session 014aA8s6qbju3vQ7x6q7vMNX)
Asked one at a time, explained simply, each logged in `DECISIONS.md` once settled (Dan, 2026-11-10).
- B1: answered (`DECISIONS.md`, "Pin map and enclosure questions"). The board B reroute of B_IN5 from PB2 to PC13 is NOT done yet; do it on a branch in its own worktree, fall back to keeping PB2 if risky.
- B2: answered 2026-11-10 (`DECISIONS.md`): CAN + USB wake only by default, each input selectable as a wake source per channel. Not built yet (firmware). Shared wake lines, one input per pair at most: board A IN_1 (PA10) / IN_3 (PC10), and IN_4 (PC11) / USB D- (PA11); board B IN_1 (PA10) / B_IN9 (PC10), B_IN10 (PC11) / USB D- (PA11), B_IN5 (PB2) / B_IN6 (PD2) until the B1 move. Checked in code: a second pin armed on the same EXTI number replaces the first (ChibiOS `hal_pal_lld.c` @ 879cf757, asserts off); any edge on CAN RX wakes it, whatever the filter says; it only sleeps after 30 s with no accepted CAN frame, all outputs off and USB unplugged.
- B3, B4, enclosure A-H (`docs/enclosure-layout.md` section 7), L1 (delete Fusion `board-A-dual` and `LINKED-COPY-unused`?): not asked yet.
- Overlap notes for the firmware / simulation session (2026-11-10, checked on `main` f473b19):
  - If the B1 reroute lands, board B `LINE_UNUSED` = PC13 collides with the new B_IN5 pin: pick another pin then.
  - B2 is answered (see above): it replaces the C3a "for now" wake-up set. Firmware work for your side, not started by this session: default wake set = no inputs (`WAKE_DIG_INPUT_MASK` 0 today is build-time only), plus a per-input "may wake" setting; the config or tool must stop two inputs of one shared wake line from both being selected, and an input sharing a line with USB D- from taking it silently. B3 and B4 are still open on this side.
  - Renode, 5 s run of `boot_a1.resc` (also with the board B binary): PC is in `Led::Code`, PC0 (error LED) is set, and the log has one "i2c1: Child address changed to 0x50, but target is not registered". So it ends in the fatal-error blink (no FRAM), not a plain idle.
  - `platforms/cpus/stm32f4.repl` is not an F446RE: flash 2 MB and RAM 256 KB (ours 512 KB / 128 KB), I2C is the `STM32F1_I2C` model, no ADC and no USB entry. Renode 1.17.0 ships no F446 platform. `Infrastructure.dll` contains the names `MB85RC` and `STM32_ADC`, nothing for MCP9808 (fit not checked).
  - Re-run on `main`: 4 ARM builds OK (31 % flash, linker RWX warning only), `s0` 36 of 36, `s1` 26 of 26.

### Open questions: firmware / simulation session (Claude-Session 014aA8s6LsbYkVVsAomAhpXK)
Kept apart from the other sessions' questions (Dan, 2026-11-10). The pin-map questions B2-B4 and the enclosure questions A-H belong to the orchestrator session: see "Waiting on Dan" above.
- None open. (D5 closed 2026-11-10: see `DECISIONS.md`.)
- Overlap notes (questions owned by the orchestrator session; listed so both sides see them, not asked by this session):
  - B2 overlap: the firmware already uses a wake-up set that follows the B2 research (all inputs except the ones sharing a wake line). Change `WAKE_DIG_INPUT_MASK` in each board's `port.h` (via `port_boards.py`) once Dan answers B2.
  - B4 overlap: the firmware already sets `LINE_UNUSED` = PC13 on board B. Revert if Dan answers B4 "no".
  - B1 overlap: board B input 5 is still on PB2 in the firmware. If the hardware move to PC13 happens, the firmware pin and `LINE_UNUSED` must change with it.

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
- 2026-11-10: Firmware port + simulation (merged to `main` the same day). Seven builds compile (A unit 1, A unit 2, B, 4 stock) with GCC 13.2.1 (cloud) and 14.2.1 (DansPC WSL); flash use 31 %. Host simulation of the real firmware logic against a board model written from the pin map: `s0_board_audit.py` 36 of 36, `s1_system.py` 26 of 26 (three boards as one 24-output PDM on stock logic, link-loss policies hold / off / on per channel). Planted wiring errors are caught. Config is 4364 / 4388 bytes (fits a 64 Kbit FRAM by size). Renode: the real board A binary boots to the ChibiOS idle thread on the stock `stm32f4` platform; no I2C FRAM / temperature sensor / ADC models yet, so it does not reach normal run. Limits and stock-firmware observations: `firmware/sim/RESULTS.md`.
- 2026-11-10: Job B merged (docs/firmware-pin-map.md): one pin table per board, timers checked against DS10693. PA8 TIM1_CH1, PB10 TIM2_CH3, PA15 TIM2_CH1, PC8 TIM8_CH3 are correct as pin functions; stock dingoFW uses software PWM, so they do not matter. Traps: B_IN5 on PB2 = BOOT1; stock LINE_UNUSED = PA15; stock debug outputs on PC10, PC11, PC13; sleep wake-up (EXTI) clashes on PC10, PC11, PD2.
- 2026-11-10: Job C merged: board B silk reference texts, one dangling PF_IN8 stub (only copper change) and Digi-Key/LCSC footprint fields are fixed by 	ools/tidy_board_b.py plus a second prune in oute_board_b.py. DRC vs stock Max: unconnected 0, clearance 7, hole_clearance 56, track_width 101, annular_width 20 unchanged. Re-import to Fusion is optional (one stub).
- 2026-11-10: Job A merged: 2D enclosure proposal (docs/enclosure-layout.md, docs/diagrams/enclosure-layout.svg, 	ools/gen_enclosure_layout.py). Inner plan 314.2 x 261.3 mm with margins that are assumptions; worst-case heat 31.1 W (hand calc); lid height TBD (J3 DT15 housing 30.1 mm or 35.3 mm, sources conflict). Nothing decided.
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
