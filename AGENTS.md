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
- `tools/build_board_a.ps1` rewrites `hardware/board-a/` in the working tree. Check `git diff --cached --stat` before every commit, and restore board files you did not mean to change (`git checkout HEAD -- hardware/board-a`).- At a finishing point, do not stop and wait: update STATE/DECISIONS/plans and working memory, then continue with the next task. Stop only for something Dan must answer or do (Dan, 2026-11-09).
