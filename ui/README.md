# ui - PC configuration tool

`dingoConfig/` is upstream dingoConfig (MIT, licence in `dingoConfig/LICENSE`), copied in the same way dingoFW lives in `firmware/` (DECISIONS 2026-11-10 B2a, K1a route A). Nothing goes upstream.

- Upstream: https://github.com/corygrant/dingoConfig, branch `development`, commit `01134ad057dee5c69788ccfecf63420740e932bc` (2026-10-26, "bump version"). It matches our firmware's dingoFW `development` @ 14084e9.
- Import commit: unmodified copy (tree hash equal to upstream `e9202a9`). Our changes are separate commits on top, so `git diff <import commit> -- ui/dingoConfig` shows all of them.
- Build output (`bin/`, `obj/`) is git-ignored.
