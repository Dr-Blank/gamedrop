#!/usr/bin/env bash
# Usage: bump-version.sh <patch|minor|major> [pre-suffix]
# Examples:
#   bump-version.sh patch       0.1.0 -> 0.1.1  (tags + prompt to push)
#   bump-version.sh minor       0.1.0 -> 0.2.0  (tags + prompt to push)
#   bump-version.sh major       0.1.0 -> 1.0.0  (tags + prompt to push)
#   bump-version.sh minor rc1   0.1.0 -> 0.2.0rc1  (commit only, no tag)
set -euo pipefail

BUMP="${1:-}"
PRE="${2:-}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -z "$BUMP" ]]; then
  echo "Usage: $0 <patch|minor|major> [pre-suffix]" >&2
  exit 1
fi

case "$BUMP" in patch|minor|major) ;; *)
  echo "Unknown bump type: $BUMP (use patch|minor|major)" >&2; exit 1 ;;
esac

CURRENT=$(cd "$REPO_ROOT/backend" && uv version)
echo "Current: $CURRENT"

# bump with native uv
(cd "$REPO_ROOT/backend" && uv version --bump "$BUMP" > /dev/null)

if [[ -n "$PRE" ]]; then
  BUMPED=$(cd "$REPO_ROOT/backend" && uv version)
  (cd "$REPO_ROOT/backend" && uv version "${BUMPED}${PRE}" > /dev/null)
fi

(cd "$REPO_ROOT/backend" && uv lock --quiet)

NEW_VERSION=$(cd "$REPO_ROOT/backend" && uv version)
echo "Bumped:  $NEW_VERSION"

cd "$REPO_ROOT"
git add backend/pyproject.toml backend/uv.lock
git commit -m "chore(release): v${NEW_VERSION}"

if [[ -z "$PRE" ]]; then
  git tag "v${NEW_VERSION}"
  echo ""
  echo "Tagged v${NEW_VERSION}. Run to publish:"
  echo "  git push && git push --tags"
else
  echo ""
  echo "Pre-release commit ready. Run to publish:"
  echo "  git push"
fi
