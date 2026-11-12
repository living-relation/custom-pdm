# STATE - custom-pdm

> **Shared document: every agent and session reads and writes this file (Dan, 2026-11-10).**
> - This is the one place for progress, open items, open questions and handoffs. It is how sessions talk to each other.
> - Keep each session's open questions in its own section. Do not edit or answer another session's section; leave a note in your own.
> - Do not copy or repeat anything from this file in any other file (docs, results, memory, handoffs). Point to it instead: `STATE.md`, section name.

Updated 2026-11-11. Decisions: `DECISIONS.md`. Scripts: `automation.yml`. Rules, git workflow and required checks: `AGENTS.md`.

**Last cleanup:** 2026-11-11 @ 8a0e5ad (repo-cleanup PR #16)
**Kept branches:** none
**Hook:** state-check workflow installed, comment mode (2026-11-08)

## Goal now
Dan's goals (orchestrator session 3): (1) finish the boards, parts and firmware; (2) full Renode bench with passing tests (done 2026-11-11); (3) enclosure with heat sink (handbuilt-cad tools + Fusion).

## Where work is
- `main`, level with `origin` (private GitHub `living-relation/custom-pdm`, re-attached 2026-11-10; PRs and the state-check workflow run again). No other branches or worktrees.
- Owner (Dan A1a, 2026-11-10): one orchestrator session plus the sub-agents it deploys. Sub-agents work in worktrees `C:\projects\active\custom-pdm\.claude\worktrees\<job>` (inside the repo root, git-ignored; rule in `AGENTS.md`) and do not edit `STATE.md` / `DECISIONS.md`; the orchestrator reviews and merges.
- Do not push anything upstream to dingoPDM / dingoFW. Do not flash anything: no hardware exists yet. Do not run two agents in Fusion at once.

## Next (in this order unless Dan says otherwise; updated 2026-11-11)
1. Digi-Key numbers for the parts changed in PR #23 / #24 (TBD in the schematic fields; `docs/parts-audit.csv` shows which).
2. Enclosure (main goal: size and appearance, cooling adapts; Dan 2026-11-12): A-G answered (e1-e7, 2026-11-12; target layout in `DECISIONS.md` 2026-11-12); next the board changes (q1a; board-stack job: DT15 off board A with wire pads in its 12 holes (a1a), J6 off board B with wire pads on its front edge (a2a); USB hub + bulkhead (y1a) to pick; input boards and JST links unchanged, x1a): DT15 removal on board A (e6a), J6 removal on board B (p1a), stacking headers on all boards (n1b, fallback JST cable), then our own 3D version (handbuilt-cad, TEST 2 as direction, rules in `DECISIONS.md` 2026-11-11/12); also firmware thermal protection and temperature-triggered fan control with a software-set limit (to plan, e3c), now that the heat analysis is done; Plan B is final (b3a). Heat results that shape them: `docs/heat-analysis.md`. Defaults rule: `AGENTS.md`.
3. Then: B2 wake firmware (see "Wake lines"); PC-side single-PDM layer research and choices for Dan (D5a; nothing exists yet, the only code is the test stand-in in `firmware/sim/s1_system.py`: `set_output`, `can_input`, `Status`); enclosure 3D only once A-H are answered.
4. Docs sweep (iterative-cleaning, Dan a2a / c1a): done 2026-11-11; fixes in `firmware/sim/RESULTS.md`, `docs/firmware-pin-map.md`, enclosure picture re-drawn after B1.

## Open questions: orchestrator session (asked one at a time, explained simply, each logged in `DECISIONS.md` once settled)
- Enclosure A-G: `docs/enclosure-layout.md` section 7 (real design choices; one at a time). On hold until testing and the heat analysis are done (Dan, 2026-11-11).
- Answered or defaulted 2026-11-11 (`DECISIONS.md`): R1-R4, B4-a, B4-c, C1, C3, C2, C4, C5 studs, C6, C7, L1, enclosure H.
- Answered: B1, B2, B3, B4-b (`DECISIONS.md`).

## Wake lines (input for the B2 firmware work)
- Shared wake lines, one input per pair at most: board A IN_1 (PA10) / IN_3 (PC10), and IN_4 (PC11) / USB D- (PA11); board B IN_1 (PA10) / B_IN9 (PC10), B_IN10 (PC11) / USB D- (PA11). The board B B_IN5 / B_IN6 pair is gone since B1 (B_IN5 on PC13).
- Checked in code: a second pin armed on the same EXTI number replaces the first (ChibiOS `hal_pal_lld.c` @ 879cf757, asserts off); any edge on CAN RX wakes it, whatever the filter says; it only sleeps after 30 s with no accepted CAN frame, all outputs off and USB unplugged.
- To build (not started): default wake set = no inputs, plus a per-input "may wake" setting. Today `WAKE_DIG_INPUT_MASK` is build-time only, set per board in `firmware/tools_custom/port_boards.py`. The config or tool must stop two inputs of one shared wake line from both being selected, and an input sharing a line with USB D- from taking it silently.

## Open items (hardware)
- Box connectors (Dan): X1 HD30 24-21 = all connector outputs (16 x 7.5 A from A1/A2 + board B OUT5-8 on size 12 cavities B, D, E, G); X2 HDP 24-47 = signals; studs = BATT, GND, board B OUT1-4. X3 dropped. Wire list in `docs/box-connectors.md`. To buy: size 20 contacts, sealing plugs, 6 studs with boots. X1 current check done: every pin is at about 60% of its TE rating; TE publishes no total-connector limit (Dan: per-pin rating is enough). Illustrations (not a source of truth): `docs/diagrams/*.svg`, drawn by `tools/gen_connector_maps.py`.
- Heat sink design: two pedestals (U8/U11 and U10/U13), insulating gap pad, pocket for J3 pins, center standoff.
- Harness: J3 pinout changed on board A (see Status).
- Review the 28 pre-existing DRC clearance findings before ordering.
- Decide 256 Kbit FRAM vs 64 Kbit substitute.
- Design the 150 A feed busbar.
- Pick connector part numbers.
- Pick fab: JLCPCB vs PCBWay.
- Board B: a human look at the layout before ordering, incl. where JP2 / JP3 ended up (render: `docs/diagrams/board-b-top-render.png`). T1-T4 courtyards overlap the BTS70012 courtyards (known); checked 2026-11-11: terminal bodies (7.1 mm square) clear every BTS70012 pad by 0.75 mm or more, and the copper they share is the same output net. Ask the assembler about the courtyard overlap at quote time.
- Small: leftover board A mask window at the old U9 spot (x -12.9..-8.94, y 11.38..14.02); the pin map still lists `LINE_SWO` for removal on board A although board B keeps it, and board A HSE crystal is by net name only; 5 schematic-parity findings on board B (stock Max 0 on this check); courtyards_overlap 10 (stock 4) and lib_footprint_issues 199 (stock 140) from the new parts.

## Status (done work, newest first)
- 2026-11-11: Heat analysis (Elmer 3D steady, `docs/heat-analysis.md`, inputs `sim/heat/`, scratch WSL `/home/daniel/scratch/heat/` 1.8 GB): TEST 2 style fins-down sink, 60 C air. Worst case 31.1 W: passive misses (sink 90-138 C depending on the convection correlation); with 2 x 30 mm fans sink about 71-75 C and every chip under Tj 150 C (hottest 121 C at pad k 3). Bottleneck is the board (9 plain vias under each BTS70012 pad, about 35 K), then the gap pad (k 1 vs 3 moves chips about 20 K). Pulling fans sit in about 74 C exhaust vs the Sunon 70 C rating; pushing keeps them at 60 C.
- 2026-11-11: `docs/parts-audit.csv` regenerated from the schematics by `tools/gen_parts_audit_csv.py` (new, in `automation.yml`; `--offline` skips LCSC lookups): 114 rows, only the PR #23 / #24 parts changed, plus board B U23-U26 now carry LCSC C534825 (added in the board fix). New parts looked up at LCSC 2026-11-12 03:21 UTC; lowest stock: MCP2562FD 903, MB85RC64TA 474 (enough for one PDM). Superseded Fusion imports deleted (u1a).
- 2026-11-11: Fusion re-import after PR #23 / #24 (`main` 549f285; KiCad 9 PCBs): folders `board-A-2026-11-11` and `board-B-2026-11-11` in project `custom-pdm`. Check vs the KiCad PCBs: board A 137 / 137 parts, 113 / 113 multi-pin nets; board B 203 / 203 parts, 139 / 139 nets (repeated pad numbers renamed `_1`.. by Fusion, same as before). `docs/diagrams/board-b-top-render.png` re-rendered with kicad-cli 10 `pcb render` (top, 1376 x 1288).
- 2026-11-11: P11 fix (PR #24, Dan p1a): D18 (A) / D4 (B) = Nexperia PMEG2010AEH (SOD-123F, LCSC C110921), footprint swapped by script, no re-route. +5V worst case 4.61 V at 25 C, about 4.52-4.55 V at -40 C (graph value; no cold max in the data sheet) vs 4.5 V CAN-chip minimum; if every TSR tolerance stacks at -40 C it could reach about 4.44 V. Ideal diode (p1b) is the fallback if cold use matters. ERC/DRC equal to main in every category. Details: `docs/parts-audit.md` section 9.
- 2026-11-11: Board-fix job (PR #23): board B 10k PB2-GND (R81); one 5 V converter per main board (TSR 1-2450, others DNP; its pins stick out about 2.3 mm under the board, clear of the pedestals, sink needs about 3 mm recess there or trimmed pins); 120 ohm + open solder jumper per main board (A: JP3 + R59, B: JP2 + R80); +12 V caps 35 V / 50 V; FRAM MB85RC64TA; CAN chip MCP2562FD-E/SN (wiring already matched); board A mask window removed; maker part numbers on changed and safety parts. Checks vs main: 0 unconnected, DRC errors equal (lib_footprint_issues +2 library-config warnings on A), ERC errors -1 per board, parity 5 -> 4. P11 found failing (+5V 4.50 V typ / 4.34 V worst vs 4.5 V CAN-chip minimum). Details and sources: `docs/parts-audit.md` section 9.
- 2026-11-11: Renode bench (PR #15): three real binaries (A1, A2, B) on one CAN hub plus an ECU / PC-tool node, 18 of 18 Robot tests pass. Re-run 2026-11-11 with `--build` from `main` after B1: 3 builds OK (linker RWX warning only), 18 of 18. Run: `powershell -ExecutionPolicy Bypass -File firmware\sim\renode\run_bench.ps1` (add `--build` to rebuild from main). Coverage, limits and findings: `firmware/sim/renode/RESULTS-renode.md`. Sandbox: WSL Ubuntu `~/renode-pdm` (Renode 1.17.0 portable, xPack arm-none-eabi-gcc 14.2.1, Python venv with Robot Framework 6.1), user-level only, remove with `rm -rf ~/renode-pdm`.
- 2026-11-11: B1 (PR #12): B_IN5 moved from PB2 to PC13 on board B, hardware plus firmware pin; `LINE_UNUSED` = PB2 as input with pull-down; wake mask 0x0FF build-time. Checks: netlist OK; ERC errors unchanged (warnings +2 off-grid); DRC same as main in every category, unconnected 0; 4 firmware builds OK; s0 36/36, s1 26/26.
- 2026-11-11: Parts audit (PR #13): every part on the three boards checked against BOM v4, datasheets and stock: `docs/parts-audit.md` (+ `.csv`), 16 problems (P1-P16) and 7 open part choices (C1-C7). Orchestrator check: the PCA82C250 CAN chip (P3) and its wiring come from stock dingoPDM v7.5 and Max (`reference/` MCU sheets), so P3 is inherited, not new.
- 2026-11-10: Firmware port + simulation, merged to `main`. `firmware/` = upstream dingoFW `d594cd7` (MIT) plus boards `custompdm_a` / `custompdm_b`; ChibiOS is a git-ignored local clone in `firmware/ChibiOS` (corygrant/ChibiOS @ 879cf757). Seven builds compile (A unit 1, A unit 2, B, 4 stock) with GCC 13.2.1 (cloud) and 14.2.1 (DansPC WSL); flash use 31 %. Host simulation of the real firmware logic against a board model written from the pin map: `s0_board_audit.py` 36 of 36, `s1_system.py` 26 of 26 (three boards as one 24-output PDM on stock logic, link-loss policies hold / off / on per channel). Planted wiring errors are caught. Config is 4364 / 4388 bytes (fits a 64 Kbit FRAM by size). Results, limits and the firmware choices made: `firmware/sim/RESULTS.md`. Board A outputs 1-2 are a BTS7008 dual pair (DSEL on the old PF_DEN2 pin, `LINE_PF1_2_DSEL`).
- 2026-11-10: Job B (`docs/firmware-pin-map.md`): one pin table per board, timers checked against DS10693. PA8 TIM1_CH1, PB10 TIM2_CH3, PA15 TIM2_CH1, PC8 TIM8_CH3 are correct as pin functions; stock dingoFW uses software PWM, so they do not matter. Traps: stock LINE_UNUSED = PA15; stock debug outputs on PC10, PC11, PC13; sleep wake-up (EXTI) clashes on PC10, PC11.
- 2026-11-10: Job C: board B silk reference texts, one dangling PF_IN8 stub (only copper change) and Digi-Key/LCSC footprint fields are fixed by `tools/tidy_board_b.py` plus a second prune in `route_board_b.py`. DRC vs stock Max: unconnected 0, clearance 7, hole_clearance 56, track_width 101, annular_width 20 unchanged.
- 2026-11-10: Job A: 2D enclosure proposal (`docs/enclosure-layout.md`, `docs/diagrams/enclosure-layout.svg`, `tools/gen_enclosure_layout.py`). Inner plan 314.2 x 261.3 mm with margins that are assumptions; worst-case heat 31.1 W (hand calc); lid height TBD (J3 DT15 housing 30.1 mm or 35.3 mm, sources conflict). Nothing decided.
- 2026-11-09 to 2026-11-10: repo was detached from GitHub (local-only); re-attached 2026-11-10 (Dan A5a). PRs before the detach: `docs/github-pr-history.md`.
- Board B (`hardware/board-b-max/`, dingoPDM-Max based, merged locally during the 2026-11-09/10 detach): schematic rebuilt by `tools/build_board_b.ps1` (baseline fe19c28 -> `tools/sch_board_b.py` -> netlist check -> ERC).
  - Added 4 x BTS7004-1EPP channels (U23-U26, sheet `BTS7004_1EPP` copied from dingoPDM MIT, RSENSE 1.2k) on page `HighCurrentDrivers2`, plus a second LM324 sense buffer (U22).
  - MCU pins: IN5-8 = PA8, PB10, PA15, PC8; DEN5_6 = PB12; DEN7_8 = PB15; IS5-8 = PA2, PA4, PA7, PC4.
  - Inputs B_IN3-10 = PC14, PC15, PC13, PD2, PB4, PB5, PC10, PC11; B_AN = PB1. PB2 (BOOT1) is the only unconnected MCU pin (B_IN5 moved off it 2026-11-11).
  - Connectors: T1-T8 bolt-down terminals, one per output, all Wuerth REDCUBE 74650074R (M4, 7 x 7 mm, 50 A at 20 C; the 85 A 74650094R is 10 x 10 mm and does not fit between a BTS70012 and its output diode). Deutsch DT header J4 removed. J6 Molex Micro-Fit 2x2 = 1 CAN_L, 2 CAN_H, 3 INPUT2, 4 INPUT1 (order follows the old J4 track ends). J7 JST GH 12 top entry (BM12B) to input board #3 (same pinout as board A J6).
  - Test points removed. Stock 4 x BTS70012 (OUT1-4) unchanged.
  - Netlist check passes. ERC: the only new errors are the same types the stock channels already have (paralleled OUT pins, GND network).
  - PCB (2026-11-10, `tools/pcb_board_b.py` then `tools/route_board_b.py`, both run by the build, about 12-13 min): board grows 39 mm to the right (72.4 -> 111.4 x 95.3 mm). Old area: T1-T4 on the four output pours, J6 where J4's centre pins were. New column: four 15 A channels whose placement and copper are copied from dingoPDM v7.5's BTS700x-1EPP block (board A baseline, MIT), turned 90 degrees, each with its terminal and output pour; bottom layer there is +12 V. A 7.5 mm strip between old edge and blocks holds J7, U22 (LM324) and R52-R55/C46. Two extra mounting holes H5/H6 (board only).
  - Routing: all 27 new nets routed (17 MCU pins fanned out with a stub + via each, tightest first; each net routed from its via). Unused fan-out vias and leftover stubs pruned; GND / +3V3 pieces cut off by new tracks re-joined.
  - DRC vs the stock Max (`tools/drc_diff.py`): 0 unconnected; clearance 7 = 7, hole clearance 56 = 56, track width 101 = 101, annular 20 = 20 (all inherited). New: 6 courtyard overlaps (terminals T1-T4 beside each other and beside the BTS70012s: bodies are 7 x 7 mm and clear), silkscreen overlaps (cosmetic).
  - Fusion: current import `board-B-2026-11-11` (see the 2026-11-11 Fusion line above).
- Input board (`hardware/input-board/`, PR #8): generated by `tools/build_input_board.ps1` (schematic text -> netlist -> KiCad 9 PCB: place, route, pour). 2-layer, 66 x 64 mm. 8 digital channels + 1 analog (0-5 V divider 10k/20k). Per channel 4.7k + BAT54S + 10 nF; 10k pull-up (SW1) / pull-down (SW2) on the wire side, Omron A6S-8104 DIPs. J2 Molex Micro-Fit 2x6 (wires: 1-8 IN, 9 analog, 10-12 GND), J1 JST GH 12 (to board A J6). ERC/DRC clean (0 unconnected, 0 parity issues). Fusion import `input-board` checked: 50/50 parts, 36/36 nets match.
- Board A inputs (PR #7, 2026-11-09), part of the default build. Fusion re-import `board-A-inputs` checked: 135/135 parts, all nets match by pin set (J1/J2/J5 multi-pad pins only renamed).
  - J6 (JST GH 12-pin, side entry) at the left edge: 1-5 IN_3..IN_7 = PC10, PC11, PB4, PC13, PB3 (ex-SWO); 6-8 NC; 9 PC2 spare analog (R12 DNP); 10 +3V3; 11-12 GND.
  - All test points removed (THT ones that joined layers got a via; dead-end stubs removed). SWO dropped. GND fenced-in pad C32.1 got a stitching via; one floating GND sliver covered by a no-fill area.
  - DRC: 0 unconnected, 0 shorts, same 28 inherited clearance findings as stock dingo. DRT logo G1 removed (Dan), so no new silkscreen notes. ERC 623 (was 632).
  - Board B (Max) check: ~9 new inputs escape without rework (PC10, PC11, PC13, PB3 + PB12, PB10, PB1, PC4, PB4). Plan ~9 there (Dan, A6a). System: 7 + 7 + ~11 = ~25 inputs.
- Board A step 1 (PR #2): U8+U9 (2x BTS7002) replaced by one BTS7008-2EPA dual at U8. J3 re-pinned: pin 7 = OUT2, pin 8 = OUT1 (was IN1), pin 12 = IN1 (was OUT2). PF_DEN2 MCU pin is now PF_DSEL1_2. PF_IS2 ADC path is spare (buffer input tied to GND). DRC/parity: 0 unconnected, no shorts, all other findings same as the unmodified dingoPDM baseline (28 clearance findings pre-exist).
- Board A design source is KiCad (`hardware/board-a/`). Rebuild it with `tools/build_board_a.ps1` (baseline + scripts, then ERC/DRC). The PCB must stay KiCad 9 format (KiCad 9.0.8 python edits it): Fusion's importer loses all nets from a KiCad 10 PCB. Schematics are KiCad 10 format upstream and import fine. kicad-cli 10 is used read-only. Fusion is for viewing, 3D and later checks (re-import after each round).
- Reference KiCad sources (dingoPDM v7.5, dingoPDM-Max) cloned locally under `reference/` (git-ignored, about 350 MB).
- dingoPDM v7.5 imported into Fusion Electronics (Fusion project `custom-pdm`, Sheets translation): design, schematic and board files created. Check: 115/115 named nets match; all 156 parts. Board checked: outline 72.39 x 95.25 mm, 4 copper layers, 522 pads, board image looks right.
- Fusion `custom-pdm` project: root = clean import of the original; current boards `board-A-2026-11-11` and `board-B-2026-11-11`; `input-board`; superseded imports deleted 2026-11-11 (u1a). `board-A-dual` and `LINKED-COPY-unused` deleted 2026-11-11 (L1).
- Part and net lists from the import are in the models folder (`Desktop\models\custom-pdm-import-check`, OneDrive, add-only).
- BOM v4 is in `docs/custom-pdm-bom-v4.xlsx` (prices are estimates, many yellow guesses).
- Plan B (3 boards on CAN, one enclosure) is final; Plan C closed (Dan b3a, 2026-11-11).

## Leftovers (each needs Dan's keep / remove call; none are in the way)
- WSL `~/renode-pdm` (2.0 GB; `dl/` holds 330 MB of downloaded archives that can go). R3 covers `bench/infra-src` inside it.
- `firmware/ChibiOS` (git-ignored local clone, needed to build). `firmware/.gitmodules` (from upstream; inert here).
- `%TEMP%\custom-pdm-fw-import\` (two import tarballs and helper scripts; the scripts that matter are already in `firmware/sim/renode/`).
- `%TEMP%\custom-pdm-parts-audit\`; `%TEMP%\board-b-build\` build outputs; B1 job temp folders `%TEMP%\bin5-build-base`, `%TEMP%\bin5-build-pc13`, `%TEMP%\bin5-stock-max`, `%TEMP%\bin5-fwcheck.*`, WSL `~/bin5-pdm`; `%TEMP%\renode-bench-2026-11-11.log*`.
- The zip sent in chat on 2026-11-10 (`custom-pdm-firmware-sim-2026-11-10.zip`) predates the C1 / C2 / D3 firmware changes: the repo is the source of truth.
- `%LOCALAPPDATA%\Workstation\claude-fusion\`: helper scripts (`call.ps1`, `up*.py`, `chk*.py`, `*.ulp`, `kicad\`), TE drawings in `te-drawings\`.

## Mistakes not to repeat
- Commit 458ef4c (2026-11-12) went to main without a PR: another session switched the shared folder to main mid-turn. Check `git branch --show-current` right before every commit; one orchestrator per repo folder.
- Committed staged files by accident twice (baseline board files in 1b16fdf; build output in `firmware/1`, `firmware/2` after passing the unit number where the output folder goes). Check `git diff --cached --stat` before every commit.
- `device_commit_files` delivered an older copy of a tarball that had just been rebuilt. Check contents after extracting.
- PowerShell `$ErrorActionPreference = 'Stop'` plus a git warning on stderr stopped a multi-step command half way. Do not combine them; send git stderr to `$null`.
- Wrote a test that assumed the stock overcurrent default was "3 tries"; it is None (the custom builds set Count, 3 tries). Read defaults from `core/param_defs.h`.
- First measured the power-up ON pulse as 4 ms because every test case had the same message timing. Vary the timing before quoting a number.
- Proposed new "front door" firmware before reading upstream; upstream already had most of it. Read the code first.
- Put one session's questions into another session's list. Keep them in the session's own section.
- Told Dan "+35 mm" for board B before laying it out; it became +39 mm. Give sizes only from a placed layout.
- Chose the 85 A terminal before checking it fits; it did not. Check footprints against the board first.
- Stated a pin shortage from a routing-only view, which reopened a decision (D1b to F1a). Count pins from the schematic.
- KiCad 9 python: `BOARD.Remove()` corrupts item lists; a python-made `NETINFO_ITEM` needs `thisown = False`; loading a second board makes the first crash on Save.
- Left debug files in the board folder and committed them; they are git-ignored now.
- Left a question ID (L1) in this file without its text; it had to be dug out of git history. Write the question with its ID.
