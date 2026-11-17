#!/usr/bin/env bash
# Fail if git tracks an agent instruction file other than AGENTS.md.
# Names: CLAUDE.md, CLAUDE.local.md, anywhere in the tree, and .claude/CLAUDE.md.
set -euo pipefail

bad=()
while IFS= read -r -d '' f; do
  base=${f##*/}
  if [ "$base" = "CLAUDE.md" ] || [ "$base" = "CLAUDE.local.md" ] || [ "$f" = ".claude/CLAUDE.md" ]; then
    bad+=("$f")
  fi
done < <(git ls-files -z)

if [ ${#bad[@]} -gt 0 ]; then
  echo "Tracked CLAUDE instruction file(s):"
  printf '  %s\n' "${bad[@]}"
  echo "Fold the content into AGENTS.md (keep every rule, drop exact duplicates) and delete the CLAUDE file in a PR."
  echo "A file inside a folder folds into that folder's AGENTS.md. A file at the repo root folds into the root AGENTS.md."
  exit 1
fi

echo "No tracked CLAUDE.md, CLAUDE.local.md, or .claude/CLAUDE.md."
