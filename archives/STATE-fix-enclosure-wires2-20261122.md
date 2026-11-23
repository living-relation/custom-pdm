# STATE (max 30 lines, overwrite only)
Repo: custom-pdm
Branch: fix/enclosure-wires2
Last_Verified_SHA: 1218983
Updated: 2026-11-22 -- wires4

## Current Goal
- Objective: enclosure revF is built, checked, published (models\custom-pdm-enclosure-revF\revF, 105 files hash ok; revE kept, revD deleted), locked (deliverable_lock OK 22) and in PR #131 (ready for review, not merged), head 1218983
- Spec_Ref: coordinator job message "wires4" 2026-11-21 (reduced scope, 7 steps); PR #131 body (checks, defaults, what the model does not prove, proposed ADR text)

## Active Blocker
- Status: NONE
- Detail: none

## Next Single Step
- [NEXT] coordinator: review / merge PR #131, take the proposed ADR-2026-11-22-enclosure-revF text into DECISIONS
- [NEXT] coordinator / Dan: delete Fusion designs CPDM-HAR-202 / -203 by hand (the API refused); decide on the locked rev B file enclosure/v2c/release/BOM-v2c-F1.csv (not touched: unlock needs Dan's word)
- [NEXT] open parts are in BACKLOG (2026-11-22 lines): USB pigtail / cable PNs, maker CAD for the drawn best-guess parts, source for the 10 mm stub rule

## Pointers
- Branch_States: none
- Backlog: BACKLOG.md
- Latest_ADR: ADR-2026-11-21-enclosure-revE
