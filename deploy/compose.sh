#!/usr/bin/env bash
# Runs docker compose for one environment on the EC2 server, with the right project, env file and
# overlays (CloudWatch logs, Litestream backups). docs/DEPLOY.md, "Production for v4".
#
#   deploy/compose.sh production up -d --build
#   deploy/compose.sh staging up -d --build
#   deploy/compose.sh staging exec backend uv run --no-dev python -m app.cli set-role --user X --role owner
#   deploy/compose.sh production logs --tail 50 backend
#
# Production reads ./.env (next to docker-compose.yml); staging reads ./.env.staging.
set -euo pipefail

cd "$(dirname "$0")/.."
environment="${1:?usage: deploy/compose.sh production|staging <docker compose arguments>}"
shift

case "$environment" in
  production) project=cochess; env_file=.env ;;
  staging) project=cochess-staging; env_file=.env.staging ;;
  *) echo "unknown environment '$environment': production or staging" >&2; exit 2 ;;
esac
if [ ! -f "$env_file" ]; then
  echo "missing $env_file (docs/DEPLOY.md)" >&2
  exit 2
fi

COCHESS_ENV="$environment" exec docker compose --env-file "$env_file" -p "$project" \
  -f docker-compose.yml -f deploy/docker-compose.aws.yml -f deploy/docker-compose.backup.yml \
  "$@"
