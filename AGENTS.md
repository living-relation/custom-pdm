# AGENTS.md - custom-pdm

Read first:
1. `STATE.md` - the ONLY place for progress, open items, PRs and handoffs.
   `DECISIONS.md` - one dated line per decision.
2. Project memory (preferences, rules, cross-project facts): `%USERPROFILE%\.claude\working-memory\custom-pdm\INDEX.md`. Never commit memory files or `CLAUDE.local.md`.

Rules:
- Sign memory notes: `-- <agent>, YYYY-MM-DD`. Absolute dates only.
- Never commit or print secrets (API keys, tokens, account details).
- Private remote (Dan, 2026-11-10): `origin` is the private GitHub repo `living-relation/custom-pdm`, kept as an off-PC backup. Never make it public (it holds dingoPDM-Max files with no license). Work on a feature branch, run the checks, push, open a PR, merge when green, then bring local `main` level with `origin/main`. Pulls are fast-forward only; never force-push; never `--no-verify`. PRs before the 2026-11-09 detach: `docs/github-pr-history.md`.
- Fusion on DansPC: follow the lock rules in `C:\projects\active\workstation\agents\projects-AGENTS.md` section 5.
- Upstream design is dingoPDM (MIT): keep its license notice on any reused files.
- `tools/build_board_a.ps1` rewrites `hardware/board-a/` in the working tree. Check `git diff --cached --stat` before every commit, and restore board files you did not mean to change (`git checkout HEAD -- hardware/board-a`).
- Worktrees and feature branches (Dan, 2026-11-11): every worktree lives inside the repo root, `C:\projects\active\custom-pdm\.claude\worktrees\<job>` (git-ignored), never beside it in `C:\projects\active` (same rule as `C:\projects\AGENTS.md`).
- Defaults (Dan, 2026-11-11): if a question only amounts to "keep going or not" and the step is a normal part of the process that breaks nothing, take the common-sense answer, log it in `DECISIONS.md` as a default, and move on. Ask Dan only about real problems or real design choices. Do not invent problems.
- At a finishing point, do not stop and wait: update STATE/DECISIONS/plans and working memory, then continue with the next task. Stop only for something Dan must answer or do (Dan, 2026-11-09).

- Other repos (Dan, 2026-11-16): st185-link-ecu-config, center-cluster-esp32-p4, realdash-dashboard-builder and any other repo are read-only for this project: read / pull only, never commit or push there without Dan's say. Copies of their content in this repo are dummy test copies (say so in the file and its name), never a source of truth, and never the only reason for a design change without Dan's approval.

- UI check (Dan, 2026-11-14): every firmware feature or setting we add must be checked against the dingo UI (dingoConfig, repo corygrant/dingoConfig; docs at corygrant/dingoElec): say whether it is shown / editable there, or list the UI change it needs.

Firmware checks (run before any commit that touches `firmware/`):
- WSL: `bash firmware/sim/renode/build_wsl.sh` (strip CR first): 4 builds OK, the only warning is the linker "RWX segment" one. Never build from `/mnt/c` (CRLF checkout): the script builds from `git archive` of a named branch (`main`).
- Linux / WSL: `firmware/sim/build.sh custompdm_a <out> 1`, same for `custompdm_a <out> 2` and `custompdm_b <out> 1`, then `python3 firmware/sim/s0_board_audit.py <out>` (expect 48 of 48), `python3 firmware/sim/s1_system.py <out>` (expect 83 of 83) and `python3 firmware/sim/s3_features.py <out>` (feature parity, `docs/feature-parity.md`: expect 92 of 92, 0 XFAIL; an XFAIL marks a gap with a proposal; exit code 0).
- Renode bench: `powershell -ExecutionPolicy Bypass -File firmware\sim\renode\run_bench.ps1 --build` (expect 32 of 32).
- Board folders are generated: change `firmware/tools_custom/port_boards.py`, re-run it, never hand-edit `firmware/boards/custompdm_*`.
