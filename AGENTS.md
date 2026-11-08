# AGENTS.md - custom-pdm

Read first:
1. `STATE.md` - the ONLY place for progress, open items, PRs and handoffs.
   `DECISIONS.md` - one dated line per decision.
2. Project memory (preferences, rules, cross-project facts): `%USERPROFILE%\.claude\working-memory\custom-pdm\INDEX.md`. Never commit memory files or `CLAUDE.local.md`.

Rules:
- Sign memory notes: `-- <agent>, YYYY-MM-DD`. Absolute dates only.
- Never commit or print secrets (API keys, tokens, account details).
- Work on a branch, open a PR; agents may merge their own PRs when green (Dan, 2026-11-08). `git pull --ff-only`; never force-push; never `--no-verify`.
- Fusion on DansPC: follow the lock rules in `C:\projects\active\workstation\agents\projects-AGENTS.md` section 5.
- Upstream design is dingoPDM (MIT): keep its license notice on any reused files.