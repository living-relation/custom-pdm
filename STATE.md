# STATE (max 30 lines, overwrite only)
Repo: custom-pdm
Branch: main
Last_Verified_SHA: 99f3f08
Updated: 2026-11-23 -- claude-cloud-orchestrator

## Current Goal
- Objective: this chat coordinates all work: PDM ready to order at JLCPCB, firmware feature parity, enclosure released, one-PDM PC tool (open, affordable, fully featured PDM)
- Spec_Ref: none

## Active Blocker
- Status: NONE
- Detail: none

## Next Single Step
- [NEXT] HOLD the order. Drift watcher (read-only agent, re-armed every 4 h via a scheduled reminder in the coordinator chat) reports; coordinator makes the repair PRs; first run 2026-11-23 07:07. Review + merge hwtemp (fix/thermal-revF), uifix2 (fix/ui-followups + CANBoard removal), carsim (feat/full-pdm-car-sim: all car loads, Link CAN, cutout, cost study); then ONE Fusion job (re-import, re-check, Fusion thermal before 2026-12-01 trial end); restart Dan app after UI merges; c6 open (Desktop Commander 83 %)

## Pointers
- Branch_States: generated (state_manager.py branches)
- Backlog: BACKLOG.md
- Latest_ADR: ADR-2026-11-23-drift-fixes
- Last_Cleanup: 2026-11-23 @ 19479b5
- Kept_Branches: fix/thermal-revF, fix/ui-followups, feat/full-pdm-car-sim (2026-11-23)
- Question_Counter: c6
