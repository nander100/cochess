#!/usr/bin/env bash
# The restore drill (SPEC_V4 §12.3; docs/DEPLOY.md, "Restore drill"): restore production's
# database as it was a few minutes ago into a new RDS instance, so staging can be pointed at it to
# prove the backups work. Nothing touches production.
#
#   DB_INSTANCE=cochess deploy/restore-drill.sh           # restore and wait (10 to 20 minutes)
#   DB_INSTANCE=cochess deploy/restore-drill.sh --delete  # remove the drill instance afterwards
#
# The drill instance uses the same subnet group and security group as production.
set -euo pipefail

SOURCE="${DB_INSTANCE:?set DB_INSTANCE to the RDS instance name (e.g. cochess)}"
REGION="${AWS_REGION:-us-east-2}"
DRILL="${SOURCE}-restore-drill"
aws() { command aws --region "$REGION" "$@"; }

if [ "${1:-}" = "--delete" ]; then
  aws rds delete-db-instance --db-instance-identifier "$DRILL" \
    --skip-final-snapshot --delete-automated-backups >/dev/null
  echo "Deleting $DRILL (it stops billing once it's gone)."
  exit 0
fi

info() {
  aws rds describe-db-instances --db-instance-identifier "$SOURCE" \
    --query "DBInstances[0].$1" --output text
}
subnets="$(info DBSubnetGroup.DBSubnetGroupName)"
groups="$(info 'VpcSecurityGroups[].VpcSecurityGroupId')"
class="$(info DBInstanceClass)"

echo "Restoring $SOURCE to its latest restorable time as $DRILL ($class) ..."
# shellcheck disable=SC2086  # $groups is a space-separated list of ids
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier "$SOURCE" --target-db-instance-identifier "$DRILL" \
  --use-latest-restorable-time --db-instance-class "$class" \
  --db-subnet-group-name "$subnets" --vpc-security-group-ids $groups \
  --no-publicly-accessible --no-multi-az --no-deletion-protection >/dev/null
aws rds wait db-instance-available --db-instance-identifier "$DRILL"
endpoint="$(aws rds describe-db-instances --db-instance-identifier "$DRILL" \
  --query 'DBInstances[0].Endpoint.Address' --output text)"
echo "Restored. Endpoint: $endpoint"
echo "Next (docs/DEPLOY.md): point staging's DATABASE_URL at it, restart staging, check"
echo "/api/health and sign in; then put staging back and run: $0 --delete"
