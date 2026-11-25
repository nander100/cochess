#!/usr/bin/env bash
# A manual RDS snapshot before a release's migrations run (SPEC_V4 §12.3; docs/DEPLOY.md,
# "Releasing"). Waits until the snapshot is available, so the deploy only starts once it's safe.
#
#   DB_INSTANCE=cochess deploy/snapshot.sh
#
# Manual snapshots stay until deleted (unlike the 14 days of automated backups): delete old ones
# in the RDS console from time to time.
set -euo pipefail

INSTANCE="${DB_INSTANCE:?set DB_INSTANCE to the RDS instance name (e.g. cochess)}"
REGION="${AWS_REGION:-us-east-2}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
revision="$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unknown)"
name="cochess-before-$revision-$(date -u +%Y%m%d-%H%M)"

echo "Snapshotting $INSTANCE as $name ..."
aws rds create-db-snapshot --region "$REGION" \
  --db-instance-identifier "$INSTANCE" --db-snapshot-identifier "$name" >/dev/null
aws rds wait db-snapshot-available --region "$REGION" --db-snapshot-identifier "$name"
echo "Snapshot $name is ready. Go ahead with the deploy."
