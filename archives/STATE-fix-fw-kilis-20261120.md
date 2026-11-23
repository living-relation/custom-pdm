# STATE (max 30 lines, overwrite only)
Repo: custom-pdm
Branch: fix/fw-kilis
Last_Verified_SHA: e7f354b
Updated: 2026-11-20 -- fwkilis worker

## Current Goal
- Objective: data-sheet kILIS per PROFET in port_boards.py; full-scale rule rechecked with the rail-to-rail IS buffer (ADR-2026-11-20-kilis)
- Spec_Ref: DECISIONS.md ADR-2026-11-20-kilis; PR #112

## Active Blocker
- Status: NONE
- Detail: none

## Next Single Step
- [NEXT] Coordinator: review and merge PR #112 (not merged by the worker); then route the 4 fwkilis BACKLOG lines (bench check of the zener chain top, stale verify_spice / pcb-verification / ui README text, rule candidate)

## Pointers
- Branch_States: none
- Backlog: BACKLOG.md
- Latest_ADR: ADR-2026-11-20-kilis
