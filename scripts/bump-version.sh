#!/bin/bash
# Bump HomePulse version in all required locations.
# Usage: ./scripts/bump-version.sh 1.3.1

set -e

if [ -z "$1" ]; then
  echo "Usage: $0 <version>"
  echo "Example: $0 1.3.1"
  exit 1
fi

VERSION="$1"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Bumping HomePulse to v${VERSION}..."

# 1. VERSION file
echo "$VERSION" > "$REPO_ROOT/VERSION"
echo "  Updated VERSION"

# 2. backend/main.py fallback version
sed -i "s/\"[0-9]\+\.[0-9]\+\.[0-9]\+\"/\"${VERSION}\"/" "$REPO_ROOT/backend/main.py"
echo "  Updated backend/main.py"

echo "Done. Don't forget to update README.md and CLAUDE.md changelogs."
