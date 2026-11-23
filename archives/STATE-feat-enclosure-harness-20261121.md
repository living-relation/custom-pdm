# STATE (max 30 lines, overwrite only)
Repo: custom-pdm
Branch: feat/enclosure-harness
Last_Verified_SHA: 1bae546
Updated: 2026-11-20 -- harness

## Current Goal
- Objective: internal enclosure wire harness in harness.design; PR open, not merged (coordinator merges)
- Spec_Ref: TASK.md (worktree root, git-ignored); harness/circuit-list.md

## Active Blocker
- Status: NONE
- Detail: open items are BACKLOG lines (12 AWG SOT yes, fan pass-through, part TBDs, on-screen app check)

## Next Single Step
- [NEXT] Coordinator: review PR feat/enclosure-harness, log the ADR text from the PR body, ask Dan the 12 AWG SOT yes; after the enclosure job models the missing routes, fill TBD lengths in the xlsx and run `python harness/src/enclosure_harness.py build` + `check`

## Pointers
- Branch_States: none
- Backlog: BACKLOG.md
- Latest_ADR: none
