#!/usr/bin/env bash
# A copy of the database just before a release's migrations run (SPEC_V4 §12.3; docs/DEPLOY.md,
# "Releasing"). Litestream already streams every change to S3; this local copy, labelled with the
# code it was taken under, is the quickest way back if a migration goes wrong.
#
#   deploy/snapshot.sh            # production
#   deploy/snapshot.sh staging
#
# Copies go to /data/backups on the database's volume; the last 5 are kept.
set -euo pipefail

environment="${1:-production}"
repo="$(cd "$(dirname "$0")/.." && pwd)"
revision="$(git -C "$repo" rev-parse --short HEAD 2>/dev/null || echo unknown)"

"$repo/deploy/compose.sh" "$environment" exec -T backend \
  uv run --no-dev python -m app.cli backup --label "before-$revision"
echo "Go ahead with the deploy."
