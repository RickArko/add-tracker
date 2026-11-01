// Exits non-zero with a one-line reason if Chromium can't start on this machine.
import { chromium } from "@playwright/test";

try {
  const browser = await chromium.launch();
  await browser.close();
} catch (error) {
  const reason = String(error.message).match(/error while loading shared libraries: [^\n]*|Executable doesn't exist[^\n]*/);
  console.error(`Chromium can't start: ${reason?.[0] ?? String(error.message).split("\n")[0]}`);
  console.error("Run scripts/setup.sh to fix this.");
  process.exit(1);
}
