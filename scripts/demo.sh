#!/usr/bin/env bash
# Runs a throwaway copy with 60 days of made-up data at http://127.0.0.1:8001.
# Never touches data/tally.db. The demo database is rebuilt on every run.
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync --quiet
[ -d frontend/node_modules ] || (cd frontend && npm ci --silent)
(cd frontend && npx vite build --logLevel warn)
export TALLY_DB_PATH=data/demo.db TALLY_SIGNUP=closed
mkdir -p data
rm -f data/demo.db data/demo.db-wal data/demo.db-shm
uv run python -m app.cli seed-demo
echo "Demo is running at http://127.0.0.1:8001"
exec uv run uvicorn --factory app.main:get_app --host 127.0.0.1 --port 8001 --log-level warning
