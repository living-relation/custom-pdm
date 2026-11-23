# STATE (max 30 lines, overwrite only)
Repo: custom-pdm
Branch: fix/board-a-current-reading
Last_Verified_SHA: none
Updated: 2026-11-23 -- isdebug

## Current Goal
- Objective: board A output current reads about 1 A low on CAN (PR #146 finding): find the root cause, fix it test-first
- Spec_Ref: docs/system-verification.md section 1; ADR-2026-11-20-kilis

## Active Blocker
- Status: NONE
- Detail: none

## Next Single Step
- [NEXT] Failing tests first (s1 S8b, Renode read-back, OutputTestLiveSimTests), then round the CAN current in port_boards.py

## Pointers
- Branch_States: none
- Backlog: BACKLOG.md
- Latest_ADR: none
