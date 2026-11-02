#!/usr/bin/env bash
# Gets a checkout ready for dev.sh, demo.sh and check.sh. Safe to run again at any time.
# Only asks for sudo if Chromium can't start because Linux system libraries are missing.
set -euo pipefail
cd "$(dirname "$0")/.."

NODE_MAJOR=24

fail() {
  echo "$1" >&2
  exit 1
}

command -v uv >/dev/null || fail "uv isn't installed. Get it from https://docs.astral.sh/uv/"
command -v node >/dev/null || fail "Node $NODE_MAJOR isn't installed. Get it from https://nodejs.org/"
[ "$(node -p 'process.versions.node.split(".")[0]')" = "$NODE_MAJOR" ] ||
  fail "This project needs Node $NODE_MAJOR, and you have $(node -v)."

echo "Installing Python packages"
uv sync --quiet

cd frontend
echo "Installing frontend packages"
npm ci --silent
echo "Installing Chromium for the browser tests"
npx playwright install chromium

if ! node e2e/browser-check.mjs >/dev/null 2>&1; then
  [ "$(uname -s)" = "Linux" ] && command -v apt-get >/dev/null ||
    fail "Chromium won't start. Run 'node frontend/e2e/browser-check.mjs' to see why."

  deps=(npx playwright install-deps chromium)
  if [ ! -t 0 ] && ! sudo -n true 2>/dev/null; then
    fail "Chromium needs system libraries, and sudo can't ask for a password here. Run this in a terminal: scripts/setup.sh"
  fi
  echo "Chromium needs system libraries. Running with sudo: ${deps[*]}"
  # sudo resets PATH, which would lose a Node installed through nvm or similar.
  sudo env "PATH=$PATH" "${deps[@]}"
  node e2e/browser-check.mjs
fi

echo "Setup is done. Next: scripts/dev.sh to run the app, or scripts/check.sh to run every check."
