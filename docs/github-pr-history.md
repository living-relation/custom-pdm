# GitHub PR history (saved before the repo was deleted)

## #1 Ignore local reference clones; update STATE (MERGED 2026-11-08T18:10:10Z)

Adds `reference/` to `.gitignore` so the local dingoPDM and dingoPDM-Max KiCad clones (about 350 MB) cannot be committed, and records the next steps in `STATE.md`.

The BOM is not in this PR yet (not on this PC).

≡ƒñû Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_014aA8s39C4B97YHNykVeLe9


> living-relation: Also on this branch: BOM v4 (docs/custom-pdm-bom-v4.xlsx) and a STATE.md update recording the dingoPDM v7.5 Fusion import (115/115 nets, 154/156 parts).

≡ƒñû Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_014aA8s39C4B97YHNykVeLe9

---

## #2 Board A: replace 2x BTS7002 with one BTS7008 dual (schematic + PCB) (MERGED 2026-11-08T19:02:10Z)

Board A: replace 2x BTS7002 (U8, U9) with one BTS7008-2EPA dual at U8.

**Schematic**
- One dual sheet; U9 group removed. DSEL uses the old PF_DEN2 MCU pin (renamed PF_DSEL1_2).
- Spare: PF_IS2 ADC path (op-amp input tied to GND) is free for an analog input.

**J3 pinout change**
| Pin | Before | After |
|---|---|---|
| 7 | OUT1 | OUT2 |
| 8 | IN1 | OUT1 |
| 12 | OUT2 | IN1 |

**PCB**
- U8 keeps its place and support parts; its output copper is split into OUT1 (pin 8) and OUT2 (pin 7).
- 3 new routes (script): U8.6-R19, U8.5-R20, J3.12-IN1.
- DRC + schematic parity: 0 unconnected, no shorts; all other findings identical to the unmodified dingoPDM baseline.

All edits are scripted in tools/ (re-runnable from the baseline commit). Files are now KiCad 10 format. STATE.md updated on this branch.

≡ƒñû Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_014aA8s39C4B97YHNykVeLe9



---

## #3 Board A: keep the PCB in KiCad 9 format (Fusion import fix) (MERGED 2026-11-08T20:10:42Z)

Fix for PR #2: the board A PCB had been saved in KiCad 10 format, and Fusion's KiCad importer lost every net from it (0 nets, 1151 loose signals).

- Rebuilt from the unmodified dingoPDM baseline with **KiCad 9.0.8** python, so the PCB stays KiCad 9 format (`version 20241229`). Schematics stay as upstream ships them (KiCad 10; Fusion reads those fine).
- One-command rebuild: `tools/build_board_a.ps1` (baseline, schematic scripts, netlist, PCB scripts, router, ERC, DRC).
- Checks: DRC + schematic parity 0 unconnected, no shorts, all other findings equal to the baseline; ERC unchanged.
- Fusion import (`custom-pdm/board-A-dual-k9`): 143 parts, 111 nets, same as KiCad.
- STATE.md updated on this branch.

≡ƒñû Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_014aA8s39C4B97YHNykVeLe9




---

## #4 Repo cleanup: DECISIONS.md, automation.yml, last-cleanup line (MERGED 2026-11-08T20:13:35Z)

Repo cleanup (repo-cleanup skill, groups approved by Dan 2026-11-08).

**Facts:** 23 decisions kept (DECISIONS.md), 0 superseded, 0 dropped, 0 asked (all are Dan's dated decisions or Claude findings he accepted).

| Group | Result |
|---|---|
| G1 local merged branches | deleted (`chore/ignore-reference`, `feat/board-a-dual-swap`, `fix/board-a-kicad9`) |
| G2 remote merged branches | deleted (same three) |
| G3 `DECISIONS.md` | new; decisions moved out of STATE.md and in from chat/memory |
| G4 STATE.md | `Last cleanup` + `Kept branches` lines |
| G5 `automation.yml` | registry of the 5 manual board A scripts |

Docs deleted: none. Starting commit: 46e5a49. Rollback: revert this PR.
Ask items open: none. Leftovers: state-file hook comes as its own PR next.

≡ƒñû Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_014aA8s39C4B97YHNykVeLe9




---

## #5 Add state-file check (comment mode) (MERGED 2026-11-08T20:18:42Z)

Adds the git-checker state-file check as a PR workflow, in **comment mode** (Dan chose option 1 on 2026-11-08).

**What it checks on every PR**
1. Real work changed (code, scripts, KiCad files; not just `.md`/`docs/`) but `STATE.md`, `DECISIONS.md` or OPEN-ITEMS wasn't updated.
2. The PR or a commit names a follow-up step that isn't written in `STATE.md`.
3. `automation.yml` matches the scripts and workflows (orphan scripts, stale or duplicate outputs).

- Comment mode: posts a warning on the PR, never fails it. Escape: `no-state-change` label.
- Switch to block mode: `bash .github/state-check.sh --mode block`, commit `.state-check-mode` via a PR.
- Uninstall: delete `.github/workflows/state-check.yml`, `.github/state-check.sh`, `.github/registry-check.py`, `.state-check-mode`.
- Files are the git-checker templates, unchanged (hashes checked). `automation.yml` cleaned up so the registry check passes locally.

≡ƒñû Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_014aA8s39C4B97YHNykVeLe9


> github-actions: WARN: code changed but STATE.md/DECISIONS.md/OPEN-ITEMS not updated (label no-state-change if intended).


---

## #6 DECISIONS: inputs and CAN (MERGED 2026-11-09T00:10:41Z)

Records Dan's 2026-11-08 decisions on inputs (on/off, ground or 12 V per input, no 5 V sensor supply, input daughter board with DT 12-pin and ribbon cable) and CAN (1 Mbps, selectable termination, open to other CAN devices).

≡ƒñû Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_014aA8s39C4B97YHNykVeLe9




---

## #7 Board A: 5 new inputs on J6, test points removed (MERGED 2026-11-09T05:17:27Z)

## What
Board A gets 5 new on/off inputs through a JST GH 12-pin locking connector (J6) at the left board edge, for the input daughter board.

| J6 pin | Signal | MCU pin |
|---|---|---|
| 1-5 | IN_3..IN_7 | PC10, PC11, PB4, PC13, PB3 (ex-SWO) |
| 6-8 | not connected (kept so the same input board fits board B) | - |
| 9 | spare analog | PC2 (R12 set DNP) |
| 10 | +3.3 V | - |
| 11-12 | GND | - |

## Why 5, not 8
Patching dingo's layout around U4 frees at most 5 more pins without disturbing dingo's own signals (tested: freeing PB5, PD2, PB13 or PA15 boxes in CAN_STANDBY, I2C or PF_DSEL3_4). Board B (dingoPDM-Max) has room for about 9 more, so the system still lands around 25 inputs (target was 16). Decisions in `DECISIONS.md`.

## Other changes
- All test points removed (Dan). Through-hole ones that joined layers become vias; dead-end stubs removed. SWO dropped.
- Router: In1.Cu tracks (USB) are now via obstacles; exact-collision fan-outs; stitching vias stay out of courtyards; routing window guard.
- `tools/build_board_a.ps1`: inputs are part of the default build; it never leaves files staged and stops on the first failing step.

## Checks
- DRC (schematic parity): 0 unconnected, 0 shorts, same 28 inherited clearance findings as stock dingoPDM. New: silkscreen notes where J6 overlaps the DRT logo (cosmetic, open question).
- ERC: 623 findings (was 632), nothing new.
- PCB stays KiCad 9 format (Fusion import).

≡ƒñû Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_014aA8s39C4B97YHNykVeLe9




---

## #8 Input board: 8 inputs + 0-5 V analog, generated by script (MERGED 2026-11-09T12:03:13Z)

## What
New input daughter board (`hardware/input-board/`), generated end to end by script so it can be rebuilt any time:
`powershell -File tools/build_input_board.ps1` (schematic -> netlist -> KiCad 9 PCB: place, route, pour -> ERC + DRC).

- 2-layer, 66 x 64 mm, 2 x M3 holes.
- 8 digital channels + 1 analog (0-5 V in, 10k/20k divider). Board A uses inputs 1-5; board B can use all 8.
- Per channel: 4.7k series, BAT54S clamp to GND/+3V3, 10 nF; 10k pull-up (SW1) and 10k pull-down (SW2) on the wire side (Omron A6S-8104 DIPs). Both off = MCU weak pull.
- J2 Molex Micro-Fit 3.0 2x6 (wires from the box connector): 1-8 inputs, 9 analog, 10-12 GND.
- J1 JST GH 12 (cable to board A J6): 1-8 inputs, 9 analog, 10 +3V3, 11-12 GND.

## Checks
- DRC with schematic parity: 0 unconnected, 0 parity issues, no clearance findings (only "library not in this configuration" notes from kicad-cli).
- ERC: only the same library-configuration notes.
- Board A rebuild unchanged after the router changes (configurable routing layers).

## Docs
STATE, DECISIONS (Dan's B1-B5 answers: max channels, Micro-Fit, 0-5 V analog, two plastic circular box connectors), automation.yml.

≡ƒñû Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_014aA8s39C4B97YHNykVeLe9


> github-actions: WARN: STALE-OUTPUT board-a-build: inputs/script changed after its outputs. Re-run: powershell -File tools/build_board_a.ps1


> github-actions: WARN: STALE-OUTPUT board-a-build: inputs/script changed after its outputs. Re-run: powershell -File tools/build_board_a.ps1


---

## #9 Box connectors: wire list and cavity map (MERGED 2026-11-09T12:26:40Z)

Adds docs/box-connectors.md: the box wall connectors with a cavity ID for each signal.

- X1 HD34-24-21SN / HD36-24-21PN: 16 x 7.5 A outputs on size 16
- X2 HDP24-24-47SE-L017 / HDP26-24-47PE-L015: 33 signals on size 20 (size 16 = 1, 4, 5, 6, 34 spare)
- X3 HDP24-24-9SE (sockets, to buy) / HDP26-24-9PE: board B 15 A / 30 A
- Cavity IDs come from TE drawing 0425-014-2400 rev H. Check the X2 numbers against the molded part.
- DECISIONS and STATE updated.

≡ƒñû Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_014aA8s39C4B97YHNykVeLe9



---

