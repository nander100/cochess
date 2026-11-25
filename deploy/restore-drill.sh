#!/usr/bin/env bash
# The restore drill (SPEC_V4 §12.3; docs/DEPLOY.md, "Restore drill"): restore production's
# backup from S3 into staging, to prove the backups work. Production is never touched.
#
#   deploy/restore-drill.sh                       # staging now runs on production's latest backup
#   deploy/restore-drill.sh 2026-12-01T09:30:00Z  # ... or as it was at that time (UTC)
#   deploy/restore-drill.sh --back                # staging back on its own backup
#
# Staging's own Litestream stays stopped while it runs on the copy, so production's data never
# lands in staging's backup. Staging's email allow list keeps it from mailing real players.
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
compose="$repo/deploy/compose.sh"
bucket="$(grep -E '^LITESTREAM_BUCKET=' "$repo/.env.staging" | cut -d= -f2-)"
region="$(grep -E '^AWS_REGION=' "$repo/.env.staging" | cut -d= -f2- || true)"
region="${region:-us-east-2}"
volume="cochess-staging_cochess-data"
image="litestream/litestream:0.5.14"
if [ -z "$bucket" ]; then
  echo "set LITESTREAM_BUCKET in .env.staging first" >&2
  exit 2
fi

restore() {  # restore <replica path> [timestamp]: replace staging's database with that backup
  local source="s3://$bucket/$1" args=()
  if [ -n "${2:-}" ]; then args=(-timestamp "$2"); fi
  "$compose" staging stop frontend backend litestream
  docker run --rm -v "$volume:/data" --entrypoint rm "$image" -f /data/restored.db
  docker run --rm -v "$volume:/data" -e AWS_REGION="$region" "$image" \
    restore "${args[@]}" -o /data/restored.db "$source"
  # Swap it in, owned like the folder (the app's user, set by the backend image).
  docker run --rm -v "$volume:/data" --entrypoint sh "$image" -c \
    'rm -f /data/cochess.db /data/cochess.db-wal /data/cochess.db-shm \
     && mv /data/restored.db /data/cochess.db && chown --reference=/data /data/cochess.db'
}

if [ "${1:-}" = "--back" ]; then
  restore staging/cochess
  "$compose" staging up -d
  echo "Staging is back on its own data, with its backups running again."
  exit 0
fi

restore production/cochess "${1:-}"
"$compose" staging up -d frontend backend  # not litestream: keep staging's backup clean
echo "Staging now runs on production's backup${1:+ as of $1}. Check it:"
echo "  curl -fsS http://127.0.0.1:8081/api/health"
echo "  sign in at https://staging.<your domain>: production's players and games should be there"
echo "Then: deploy/restore-drill.sh --back"
