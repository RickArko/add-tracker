#!/usr/bin/env bash
# Every quality gate from docs/BUILD_PLAN.md. Stops at the first failure.
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync --quiet
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
cd frontend
node e2e/browser-check.mjs
npx vue-tsc --noEmit
npx vitest run --silent
npx vite build --logLevel warn
npx playwright test --reporter=line
