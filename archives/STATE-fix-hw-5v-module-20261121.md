# STATE (max 30 lines, overwrite only)
Repo: custom-pdm
Branch: fix/hw-5v-module
Last_Verified_SHA: none
Updated: 2026-11-21 -- hw5v

## Current Goal
- Objective: 125 C 5 V module (TI LMZM23601V5) in place of TSR 1-2450 at B U13 (-> U27) / A U15 (-> U21); PR open, not merged
- Spec_Ref: TASK.md (worktree .claude/worktrees/hw5v); coordinator default 2026-11-21 (least redesign, no enclosure change)

## Active Blocker
- Status: NONE
- Detail: none

## Next Single Step
- [NEXT] Coordinator: review the PR, add the proposed ADR (PR body) to DECISIONS, merge when green (no firmware change, no sim rebuild); remove scratch worktree .claude/worktrees/hw5v-base (detached 4acc512, read-only baseline)

## Pointers
- Branch_States: none
- Backlog: BACKLOG.md (hw5v lines 2026-11-21: TSR line closed, bench tests)
- Latest_ADR: proposed ADR-2026-11-21-5v-module in the PR body (reopens the U13 item of ADR-2026-11-20-hwprotect)
