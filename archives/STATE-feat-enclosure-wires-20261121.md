# STATE (max 30 lines, overwrite only)
Repo: custom-pdm
Branch: feat/enclosure-wires
Last_Verified_SHA: fa6511d
Updated: 2026-11-21 -- wires

## Current Goal
- Objective: enclosure revE (real round 3D wires, harness subassembly CPDM-HAR-200) is built, checked, published (models\custom-pdm-enclosure-revE\revE, 90 files hash ok; revD kept, revC deleted), locked (deliverable_lock OK 20) and in PR #130 (open, not merged; main 915ae54 merged in)
- Spec_Ref: coordinator job message "wires" 2026-11-21 (7 steps); PR #130 body (checks, defaults, proposed ADR text)

## Active Blocker
- Status: NONE
- Detail: none (open design items are in the PR body "Found")

## Next Single Step
- [NEXT] coordinator: review / merge PR #130, take the proposed ADR text into DECISIONS; Dan decision needed: USB hub stands 1.5 mm in front of board B USB-C (no plug fits; cable U2 is a stub)
- [NEXT] later job: real TE cavity map for X1 / X2 (now an ASSUMED ring pattern), then untangle the 118 wire-on-wire overlaps in the fan-outs (wirecheck_v2c.py lists them)
- [NEXT] coordinator tidy-up: Fusion designs CPDM-HAR-202 / -203 unused in Parts; enclosure/v2c/release/BOM-v2c-F1.csv still revD's (locked); scratch kept for follow-ups: WSL ~/scratch/wires, %TEMP%\wires (old cadfetch / encl-v2c-revD scratch cleared)

## Pointers
- Branch_States: none
- Backlog: BACKLOG.md
- Latest_ADR: ADR-2026-11-20-enclosure-revD
