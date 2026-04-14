#!/bin/bash
# Bump HomePulse version in all required locations (per CLAUDE.md checklist):
#   1. VERSION
#   2. backend/main.py fallback string
#   3. CLAUDE.md — all "(currently X.Y.Z)" / "(current)" references
#   4. README.md — versioning list (manual changelog entry still required)
#
# Usage: ./scripts/bump-version.sh <new-version>
# Example: ./scripts/bump-version.sh 2.0.0

set -e

if [ -z "$1" ]; then
  echo "Usage: $0 <version>"
  echo "Example: $0 2.0.0"
  exit 1
fi

NEW="$1"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OLD="$(cat "$REPO_ROOT/VERSION" | tr -d '[:space:]')"

if [ "$OLD" = "$NEW" ]; then
  echo "Already at v${NEW} — nothing to do."
  exit 0
fi

echo "Bumping HomePulse: v${OLD} -> v${NEW}"

# 1. VERSION file
echo "$NEW" > "$REPO_ROOT/VERSION"
echo "  Updated VERSION"

# 2. backend/main.py fallback version string (the literal "X.Y.Z" near __version__)
sed -i "s/\"${OLD}\"/\"${NEW}\"/g" "$REPO_ROOT/backend/main.py"
echo "  Updated backend/main.py"

# 3. CLAUDE.md — swap every occurrence of the old version for the new one
if [ -f "$REPO_ROOT/CLAUDE.md" ]; then
  sed -i "s/${OLD}/${NEW}/g" "$REPO_ROOT/CLAUDE.md"
  echo "  Updated CLAUDE.md"
fi

# 4. README.md — swap every occurrence of the old version for the new one
if [ -f "$REPO_ROOT/README.md" ]; then
  sed -i "s/${OLD}/${NEW}/g" "$REPO_ROOT/README.md"
  echo "  Updated README.md"
fi

echo
echo "Done. Manual follow-ups:"
echo "  - Add a new changelog entry at the top of README.md describing v${NEW}"
echo "  - Review the sed pass above for any unintended replacements"
