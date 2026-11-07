#!/usr/bin/env bash
set -euo pipefail

# Run on the VPS from an extracted, immutable release directory.
cd "$(dirname "$0")/.."
test -r /etc/cp-hub/backend.env
compose=(docker compose --project-name cp-hub --env-file /etc/cp-hub/backend.env -f deploy/compose.yml)
"${compose[@]}" build api
"${compose[@]}" up -d --wait db
"${compose[@]}" run --rm --no-deps api uv run --locked --no-dev alembic upgrade head
"${compose[@]}" up -d --no-deps api
curl --fail --silent --show-error --max-time 5 --retry 15 --retry-delay 2 --retry-all-errors \
  http://127.0.0.1:8000/health
