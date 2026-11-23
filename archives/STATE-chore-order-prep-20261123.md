# STATE (max 30 lines, overwrite only)
Repo: custom-pdm
Branch: chore/order-prep
Last_Verified_SHA: none
Updated: 2026-11-23 -- orderprep finish worker

## Current Goal
- Objective: order prep PR #133 MERGED 2026-11-23 as 3a90493 (board A + B 1 oz / 1 oz copper, order checklist checked against JLCPCB's live quote page); local main ff'd; worktrees orderprep + orderprep-rebuild removed, branch deleted (local + origin)
- Spec_Ref: TASK.md (moved out of the worktree to %TEMP%\orderprep-TASK.md before removal)

## Active Blocker
- Status: NONE
- Detail: none

## Next Single Step
- [NEXT] Coordinator: add ADR-2026-11-22-copper to DECISIONS: boards A and B 4-layer with 1 oz outer and 1 oz inner (Dan c1 = a; board A matched as a coordinator default)
- [NEXT] Coordinator: rebuild the shared UI sim .so from main if wanted (firmware code unchanged by this PR: comment lines only)
- [NEXT] Coordinator decides: JLCPCB default Material Type is FR4 TG135 while board B laminate runs 117-118 C at 150 A (TG155 is one option on the quote page); kept the default in docs/order-checklist.md

## Pointers
- Branch_States: none
- Backlog: BACKLOG.md
- Latest_ADR: ADR-2026-11-22-enclosure-revF (proposed next: ADR-2026-11-22-copper, PR #133 body)
