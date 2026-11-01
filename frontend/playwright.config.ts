import { defineConfig } from "@playwright/test";

const PORT = 8765;
const db = process.env.TALLY_E2E_DB ?? `/tmp/tally-e2e-${process.pid}.db`;

export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    screenshot: "only-on-failure",
    launchOptions: process.env.TALLY_CHROMIUM
      ? { executablePath: process.env.TALLY_CHROMIUM }
      : {},
  },
  webServer: {
    command: `uv run uvicorn --factory app.main:get_app --host 127.0.0.1 --port ${PORT}`,
    cwd: "..",
    url: `http://127.0.0.1:${PORT}/healthz`,
    reuseExistingServer: false,
    env: { TALLY_DB_PATH: db, TALLY_SIGNUP: "open" },
  },
});
