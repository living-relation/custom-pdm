# State protocol (always on)

Enforcer: `state_lint.py` (store STATE files), CI `state-check` (comment mode), the workstation-core skills (session-start, state-closeout, pr-closeout).

- Live state lives only in the memory store (`state_paths.py --repo .`): `STATE.md` = the single coordinator chat; `STATE-<slug>.md` = one worker each (slug = branch name, lowercase, other characters as `-`); `BACKLOG.md` append only (close an item with a new `[closed <date>] <item>` line); `archives/`. No progress, open items, handoffs or STATE file in the repo, and none in memory notes.
- STATE schema v1, 30 lines max, overwritten each time; only `[NEXT]` lines stay in a STATE file. The root STATE Pointers may hold `Question_Counter`, `Last_Cleanup`, `Kept_Branches`; `Branch_States` is generated (`state_manager.py branches`), never typed.
- Seven tags: `[DONE]` (dropped: git history is the record), `[NEXT]` (stays), `[TASK]` (`TASK.md` of the branch), `[ADR]` (DECISIONS), `[RULE]` (`.claude/rules/<domain>.md` + rules_sync), `[SOT]` (data files, only after Dan's yes; until then a BACKLOG line marked `needs owner yes`), `[BKLG]` (BACKLOG). A line carried through two closeouts must graduate.
- Run state-closeout at 80 % context, on a pivot, a blocker, a milestone and every PR (pr-closeout writes the PR body `State:` line). Handoffs: `state-closeout handoff` prints a paste block; the STATE-<slug> file is the handoff.
- Workers write only their own `STATE-<slug>.md` and BACKLOG lines; the coordinator owns the root STATE, DECISIONS and the router. Every user answer goes to its home in the same turn, with the date.
- Finished deliverables (fab outputs, enclosure releases, drawings) are locked with `deliverable_lock.py` (`VERIFIED.lock`, `Last_Verified_SHA` in STATE); a locked file that changed without Dan's unlock is a regression (regression-restore).
- Never do: leave a question ID without its text (L1 had to be dug out of git history, 2026-11); put one session's questions into another session's list.
