# STATE (max 30 lines, overwrite only)
Repo: custom-pdm
Branch: fix/hw-sense-tvs-feed
Last_Verified_SHA: none
Updated: 2026-11-20 -- claude-cloud-hwfix

## Current Goal
- Objective: ADR-2026-11-20 is-buffer (TLV9004IPWR), tvs-loaddump, boardb-feed: carry out, prove with tools/verify_*.py, one PR (no merge)
- Spec_Ref: TASK.md (worktree root)

## Active Blocker
- Status: BLOCKED
- Detail: TVS D2: SM8S24CA (DO-218AB) passes but does not fit at D2 without moving D2 or C2 / J1: coordinator + enclosure job (parts-audit 14.3)

## Next Single Step
- [NEXT] coordinator: review the PR; decide the D2 footprint move (TVS), then a follow-up job fits SM8S24CAHM3/I

## Pointers
- Branch_States: none
- Backlog: BACKLOG.md
- Latest_ADR: ADR-2026-11-20-boardb-feed
