# STATE (max 30 lines, overwrite only)
Repo: custom-pdm
Branch: main
Last_Verified_SHA: 033cc60
Updated: 2026-11-23 -- claude-cloud-orchestrator

## Current Goal
- Objective: this chat coordinates all work: PDM ready to order at JLCPCB, firmware feature parity, enclosure released, one-PDM PC tool (open, affordable, fully featured PDM)
- Spec_Ref: none

## Active Blocker
- Status: NONE
- Detail: none

## Next Single Step
- [NEXT] HOLD the order. Review + merge hwtemp (fix/thermal-revF), carsim (feat/full-pdm-car-sim), isdebug (fix/board-a-current-reading); then ONE Fusion job (re-import changed boards, re-check, Fusion thermal per board + assembly before the 2026-12-01 trial end); move the old store state copies to the store _archive; drift watcher every 4 h (coordinator reminder)

## Pointers
- Branch_States: generated (state_manager.py branches)
- Backlog: BACKLOG.md
- Latest_ADR: ADR-2026-11-23-uifix2
- Last_Cleanup: 2026-11-23 @ 19479b5
- Kept_Branches: fix/thermal-revF, feat/full-pdm-car-sim, fix/board-a-current-reading (2026-11-23)
- Question_Counter: c6
