#!/usr/bin/env bash
# Runs the app at http://127.0.0.1:8000 using your real data in data/tally.db.
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync --quiet
[ -d frontend/node_modules ] || (cd frontend && npm ci --silent)
(cd frontend && npx vite build --logLevel warn)
echo "Tally is running at http://127.0.0.1:8000"
exec uv run uvicorn --factory app.main:get_app --host 127.0.0.1 --port 8000
