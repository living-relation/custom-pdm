# STATE (max 30 lines, overwrite only)
Repo: custom-pdm
Branch: feat/pcb-verify
Last_Verified_SHA: none
Updated: 2026-11-20 -- claude-cloud-pcbverify

## Current Goal
- Objective: automated PCB verification (rule checks, current density, SPICE, SI) replaces a human layout look; pass / fail report per board
- Spec_Ref: docs/pcb-verification.md

## Active Blocker
- Status: NONE
- Detail: PR open, not merged (coordinator merges); 3 design choices in docs/pcb-verification.md "Left" (BACKLOG lines 2026-11-20)

## Next Single Step
- [NEXT] coordinator: decide docs/pcb-verification.md Left 1-3 (board B +12V copper, TVS vs load dump, IS buffer op-amp), then merge feat/pcb-verify

## Pointers
- Branch_States: none
- Backlog: BACKLOG.md
- Latest_ADR: ADR-2026-11-19-state-layout
