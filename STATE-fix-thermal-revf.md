# STATE (max 30 lines, overwrite only)
Repo: custom-pdm
Branch: fix/thermal-revF
Last_Verified_SHA: f9143d8
Updated: 2026-11-23 -- hwtemp worker

## Current Goal
- Objective: PR #139 heat fixes: 5 V module loss from TI data (0.131 W), FRAM -> CY15B064J-SXE (125 C), board A limits 98 / 104 / 6, input-board DIP -> solder jumpers JP1-16, fans WARN kept; s5 drive case; UI offsets A 19.8 / B 20.0 K
- Spec_Ref: none

## Active Blocker
- Status: NONE
- Detail: none

## Next Single Step
- [NEXT] check board A / B rebuild diff (keep only U5 fields), commit, WSL firmware builds + s0/s1/s3/s4/s5 + Renode + md5, dotnet test, docs (heat-analysis 0/5, system-verification), merge origin/main, PR, merge, remove worktree .claude/worktrees/hwtemp

## Pointers
- Branch_States: generated (state_manager.py branches)
- Backlog: BACKLOG.md
- Latest_ADR: ADR-2026-11-23-canboard
