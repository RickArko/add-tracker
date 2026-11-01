import { defineConfig } from "@playwright/test";

const PORT = 8765;
// Kept in the environment so test workers can reach the same file.
process.env.TALLY_E2E_DB ??= `/tmp/tally-e2e-${process.pid}.db`;
const db = process.env.TALLY_E2E_DB;
process.env.TALLY_E2E_OUTBOX ??= `/tmp/tally-e2e-${process.pid}.mail`;

export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    screenshot: "only-on-failure",
    // On for the offline test only; a worker would hide requests from other tests' checks.
    serviceWorkers: "block",
    launchOptions: process.env.TALLY_CHROMIUM
      ? { executablePath: process.env.TALLY_CHROMIUM }
      : {},
  },
  webServer: {
    command: `uv run uvicorn --factory app.main:get_app --host 127.0.0.1 --port ${PORT}`,
    cwd: "..",
    url: `http://127.0.0.1:${PORT}/healthz`,
    reuseExistingServer: false,
    env: {
      TALLY_DB_PATH: db,
      TALLY_SIGNUP: "open",
      TALLY_EMAIL_OUTBOX: process.env.TALLY_E2E_OUTBOX,
      TALLY_EMAIL_PEPPER: "test-only",
      TALLY_PUBLIC_URL: `http://127.0.0.1:${PORT}`,
    },
  },
});
