# STATE (max 30 lines, overwrite only)
Repo: custom-pdm
Branch: fix/fw-safety
Last_Verified_SHA: ae7683e
Updated: 2026-11-20 -- fwsafety

## Current Goal
- Objective: BOR level 3 at boot, IWDG with check-ins + RTC-refreshed sleep, board B thermal defaults 98 / 104 C, motor PWM / pair limits in the UI presets (PR #117)
- Spec_Ref: TASK.md (worktree root), ADR-2026-11-20-presim-findings items 1 / 2 / 3

## Active Blocker
- Status: NONE
- Detail: none

## Next Single Step
- [NEXT] coordinator: review PR #117 (all checks green at ae7683e), log its defaults in DECISIONS, answer the u1a temperature-set question with Dan, merge

## Pointers
- Branch_States: none
- Backlog: BACKLOG.md
- Latest_ADR: ADR-2026-11-20-presim-findings
