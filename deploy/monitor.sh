#!/usr/bin/env bash
# Publishes CoChess's health metrics to CloudWatch (SPEC_V4 §12.3; docs/DEPLOY.md, "Monitoring").
# Run by cron on the EC2 server every minute, once per environment:
#
#   * * * * * COCHESS_ENV=production /home/ubuntu/cochess/deploy/monitor.sh
#   * * * * * COCHESS_ENV=staging HEALTH_URL=http://127.0.0.1:8081/api/health \
#             /home/ubuntu/cochess/deploy/monitor.sh
#
# Every minute: HealthOk (1 when /api/health answers 200, else 0), DiskUsedPercent, and
# BackupRunning (1 while the Litestream container runs).
# At minute 0 of each hour: ApiSpend24hUSD, the coach's API cost over the last 24 hours.
# Uses the instance's IAM role (cloudwatch:PutMetricData). Prints nothing on success.
set -euo pipefail

ENVIRONMENT="${COCHESS_ENV:-production}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8080/api/health}"
REGION="${AWS_REGION:-us-east-2}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"

put() {  # put <metric> <value> <unit>
  aws cloudwatch put-metric-data --region "$REGION" --namespace CoChess \
    --metric-name "$1" --value "$2" --unit "$3" \
    --dimensions "Environment=$ENVIRONMENT"
}

healthy=0
if curl -fsS --max-time 10 "$HEALTH_URL" >/dev/null 2>&1; then
  healthy=1
fi
put HealthOk "$healthy" Count

used="$(df --output=pcent / | tail -1 | tr -dc '0-9')"
put DiskUsedPercent "$used" Percent

running=0
if [ -n "$("$REPO/deploy/compose.sh" "$ENVIRONMENT" ps --status running -q litestream 2>/dev/null)" ]; then
  running=1
fi
put BackupRunning "$running" Count

if [ "$(date +%M)" = "00" ]; then
  spend="$("$REPO/deploy/compose.sh" "$ENVIRONMENT" exec -T backend \
    uv run --no-dev python -m app.cli spend --hours 24)"
  put ApiSpend24hUSD "$spend" None
fi
