// Exits non-zero with a one-line reason if Chromium can't start on this machine.
import { chromium } from "@playwright/test";

try {
  // The same override playwright.config.ts uses, so this checks the browser the tests will run.
  const executablePath = process.env.TALLY_CHROMIUM || undefined;
  const browser = await chromium.launch({ executablePath });
  await browser.close();
} catch (error) {
  const reason = String(error.message).match(/error while loading shared libraries: [^\n]*|Executable doesn't exist[^\n]*/);
  console.error(`Chromium can't start: ${reason?.[0] ?? String(error.message).split("\n")[0]}`);
  console.error(process.env.TALLY_CHROMIUM ? "Check the path in TALLY_CHROMIUM." : "Run scripts/setup.sh to fix this.");
  process.exit(1);
}
