#!/usr/bin/env bash
# Creates CoChess's alarms in CloudWatch, emailed to the owner (SPEC_V4 §12.3; docs/DEPLOY.md,
# "Monitoring"). Safe to run again: every call creates or updates the same names.
#
#   deploy/alarms.sh you@example.com                      # production
#   COCHESS_ENV=staging deploy/alarms.sh you@example.com  # staging
#
# Settings (environment): AWS_REGION (us-east-2), SPEND_LIMIT_USD (5: API cost in 24 hours),
# BUDGET_USD (30: the monthly AWS budget, production only).
#
# Alarms: the health check failing for 3 minutes (or not reported at all), disk above 80%, the
# Litestream backup not running for 5 minutes, 5+
# backend errors in 5 minutes, 3+ Anthropic errors in 5 minutes, any payment error, API spend
# over the limit; plus the AWS budget. Confirm the subscription email AWS sends you first.
set -euo pipefail

EMAIL="${1:?usage: deploy/alarms.sh you@example.com}"
ENVIRONMENT="${COCHESS_ENV:-production}"
REGION="${AWS_REGION:-us-east-2}"
SPEND_LIMIT="${SPEND_LIMIT_USD:-5}"
BUDGET="${BUDGET_USD:-30}"
LOGS="/cochess/$ENVIRONMENT/backend"
aws() { command aws --region "$REGION" "$@"; }

topic="$(aws sns create-topic --name "cochess-alarms-$ENVIRONMENT" --query TopicArn --output text)"
aws sns subscribe --topic-arn "$topic" --protocol email --notification-endpoint "$EMAIL" >/dev/null
echo "Alarms go to $EMAIL (confirm the email from AWS Notifications) via $topic"

# Counts from the backend's JSON logs (app/logs.py).
aws logs create-log-group --log-group-name "$LOGS" 2>/dev/null || true
filter() {  # filter <metric> <pattern>
  aws logs put-metric-filter --log-group-name "$LOGS" --filter-name "$1" \
    --filter-pattern "$2" --metric-transformations \
    "metricName=$1,metricNamespace=CoChess/$ENVIRONMENT,metricValue=1,defaultValue=0"
}
filter BackendErrors '{ $.level = "ERROR" }'
filter AnthropicErrors '{ $.message = "anthropic request failed*" }'
filter PaymentErrors '{ ($.level = "ERROR") && ($.logger = "app.billing") }'

# alarm <name> <namespace> <metric> <statistic> <operator> <threshold> <periods> <missing> [dims]
alarm() {
  local dimensions=()
  if [ -n "${9:-}" ]; then dimensions=(--dimensions "$9"); fi
  aws cloudwatch put-metric-alarm --alarm-name "cochess-$ENVIRONMENT-$1" \
    --namespace "$2" --metric-name "$3" --statistic "$4" \
    --comparison-operator "$5" --threshold "$6" --evaluation-periods "$7" \
    --period 60 --treat-missing-data "$8" "${dimensions[@]}" \
    --alarm-actions "$topic" --ok-actions "$topic"
}
env="Name=Environment,Value=$ENVIRONMENT"
ours="CoChess/$ENVIRONMENT"
alarm health-failing CoChess HealthOk Minimum LessThanThreshold 1 3 breaching "$env"
alarm disk-above-80 CoChess DiskUsedPercent Maximum GreaterThanThreshold 80 5 missing "$env"
alarm backup-stopped CoChess BackupRunning Minimum LessThanThreshold 1 5 breaching "$env"
alarm backend-errors "$ours" BackendErrors Sum GreaterThanOrEqualToThreshold 5 5 notBreaching
alarm anthropic-errors "$ours" AnthropicErrors Sum GreaterThanOrEqualToThreshold 3 5 notBreaching
alarm payment-errors "$ours" PaymentErrors Sum GreaterThanOrEqualToThreshold 1 1 notBreaching
alarm api-spend CoChess ApiSpend24hUSD Maximum GreaterThanThreshold "$SPEND_LIMIT" 1 \
  notBreaching "$env"
echo "Alarms set for $ENVIRONMENT."

if [ "$ENVIRONMENT" = production ]; then
  account="$(aws sts get-caller-identity --query Account --output text)"
  limit="{\"Amount\":\"$BUDGET\",\"Unit\":\"USD\"}"
  budget="{\"BudgetName\":\"cochess-monthly\",\"BudgetLimit\":$limit,\"TimeUnit\":\"MONTHLY\",\"BudgetType\":\"COST\"}"
  when="{\"NotificationType\":\"ACTUAL\",\"ComparisonOperator\":\"GREATER_THAN\",\"Threshold\":80}"
  notify="[{\"Notification\":$when,\"Subscribers\":[{\"SubscriptionType\":\"EMAIL\",\"Address\":\"$EMAIL\"}]}]"
  if aws budgets describe-budget --account-id "$account" --budget-name cochess-monthly >/dev/null 2>&1; then
    aws budgets update-budget --account-id "$account" --new-budget "$budget"
  else
    aws budgets create-budget --account-id "$account" --budget "$budget" \
      --notifications-with-subscribers "$notify"
  fi
  echo "AWS budget: \$$BUDGET a month, emailed at 80%."
fi
