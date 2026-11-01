import AxeBuilder from "@axe-core/playwright";
import { DatabaseSync } from "node:sqlite";
import { expect, test, type Page } from "@playwright/test";

const PASSPHRASE = "correct horse battery";
const unique = () => `user${Date.now()}${Math.floor(Math.random() * 1000)}`;

/** Fails any test where the page hits a CSP error, console error, or another host. */
function watchPage(page: Page) {
  const problems: string[] = [];
  page.on("console", (m) => {
    // 4xx from deliberately wrong logins surface as console errors; those are expected.
    if (m.type() === "error" && !m.text().includes("status of 4")) problems.push(m.text());
  });
  page.on("pageerror", (e) => problems.push(String(e)));
  page.on("request", (r) => {
    if (new URL(r.url()).hostname !== "127.0.0.1") problems.push(`external request: ${r.url()}`);
  });
  return problems;
}

async function register(page: Page, name = unique()) {
  await page.goto("/login");
  const create = page.getByRole("button", { name: "Create an account" });
  if (await create.isVisible()) await create.click();
  await page.getByLabel("Username").fill(name);
  await page.getByLabel("Passphrase").fill(PASSPHRASE);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("What do you want to keep track of?")).toBeVisible();
  return name;
}

async function addAlcohol(page: Page) {
  await page.getByRole("button", { name: "Alcohol" }).click();
  await page.getByLabel("Daily limit").fill("2");
  await page.getByRole("button", { name: "Start tracking" }).click();
  await expect(page.getByRole("heading", { name: "Alcohol" })).toBeVisible();
}

test("logged-out visitors can only reach log in and support", async ({ page }) => {
  await page.goto("/trends");
  await expect(page).toHaveURL(/\/login$/);
  await page.getByRole("link", { name: "Need support right now?" }).click();
  await expect(page.getByRole("heading", { name: "Get support" })).toBeVisible();
  await expect(page.getByRole("link", { name: "988" })).toBeVisible();
});

test("the core loop: track, log, undo, add details, see trends and history", async ({ page }) => {
  const problems = watchPage(page);
  await register(page);

  // Safety note appears for a goal where sudden stopping can be dangerous.
  await page.getByRole("button", { name: "Alcohol" }).click();
  await expect(page.getByText("sharply cutting back can cause seizures")).toBeVisible();
  await page.getByLabel("Daily limit").fill("2");
  await page.getByRole("button", { name: "Start tracking" }).click();

  const log = page.getByRole("button", { name: "Log 1 drink" });
  await log.click();
  await expect(page.getByText("1 of 2 drinks today")).toBeVisible();
  await expect(page.getByRole("img", { name: "1 logged" })).toBeVisible();

  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByText("0 of 2 drinks today")).toBeVisible();

  // Six taps: state must match the server, and marks must bundle into a five and a one.
  for (let i = 0; i < 6; i++) await log.click();
  await expect(page.getByText("6 of 2 drinks today")).toBeVisible();
  await page.reload();
  await expect(page.getByText("6 of 2 drinks today")).toBeVisible();
  await expect(page.locator(".tally svg")).toHaveCount(2);
  await expect(page.locator(".tally path")).toHaveCount(6);

  await page.getByRole("button", { name: "Had an urge, didn't use" }).click();
  await expect(page.getByText("1 urge without use")).toBeVisible();
  await page.getByRole("button", { name: "Add details" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "7", exact: true }).click();
  await dialog.getByRole("button", { name: "Stress" }).click();
  await dialog.getByLabel("Note").fill("hard meeting");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toBeHidden();

  await page.getByRole("link", { name: "Trends" }).click();
  await expect(page.getByText("Average craving")).toBeVisible();
  await expect(page.getByText("7 out of 10")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Use per day" })).toBeVisible();
  await expect(page.locator(".chart path.bar")).toHaveCount(1);
  await expect(page.getByText("0 used, 1 urge")).toBeVisible();
  await page.getByRole("button", { name: "90 days" }).click();
  await page.getByText("Show as a table").click();
  await expect(page.locator(".table-view tbody tr")).toHaveCount(1);

  await page.getByRole("link", { name: "History" }).click();
  await expect(page.getByText("hard meeting")).toBeVisible();
  await page.getByText("hard meeting").click();
  await page.getByRole("dialog").getByRole("button", { name: "Delete entry" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Confirm delete" }).click();
  await expect(page.getByText("hard meeting")).toBeHidden();

  expect(problems).toEqual([]);
});

test("a backdated edit moves the entry to the earlier day", async ({ page }) => {
  await register(page);
  await addAlcohol(page);
  await page.getByRole("button", { name: "Log 1 drink" }).click();
  await page.getByRole("button", { name: "Add details" }).click();
  const yesterday = new Date(Date.now() - 86_400_000);
  const pad = (n: number) => String(n).padStart(2, "0");
  const value = `${yesterday.getFullYear()}-${pad(yesterday.getMonth() + 1)}-${pad(yesterday.getDate())}T12:00`;
  await page.getByRole("dialog").getByLabel("When").fill(value);
  await page.getByRole("dialog").getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("0 of 2 drinks today")).toBeVisible();
});

test("today uses the device time zone, not the server's", async ({ browser }) => {
  // One minute past Auckland's midnight is usually another calendar day in UTC.
  const name = unique();
  const here = await browser.newContext({ timezoneId: "Pacific/Auckland" });
  const page = await here.newPage();
  await register(page, name);
  await addAlcohol(page);
  const midnight = await page.evaluate(() => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return new Date(d.getTime() + 60_000).toISOString();
  });
  const [tracker] = await page.evaluate(() => fetch("/api/trackers").then((r) => r.json()));
  await page.evaluate(
    ([id, when]) =>
      fetch("/api/entries", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tracker_id: id, occurred_at: when }),
      }),
    [tracker.id, midnight],
  );
  await page.reload();
  await expect(page.getByText("1 of 2 drinks today")).toBeVisible();
  await here.close();
});

test("rapid taps while a reload lands keep the right count", async ({ page }) => {
  await register(page);
  await addAlcohol(page);
  await page.route("**/api/entries", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 300));
    await route.continue();
  });
  const log = page.getByRole("button", { name: "Log 1 drink" });
  await log.click();
  await log.click();
  await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
  await log.click();
  await expect(page.getByText("3 of 2 drinks today")).toBeVisible();
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("3 of 2 drinks today")).toBeVisible();
});

test("a hidden tracker stays reachable in Trends", async ({ page }) => {
  await register(page);
  await addAlcohol(page);
  await page.goto("/settings");
  await page.getByRole("button", { name: "Hide" }).click();
  await expect(page.getByText("Hidden from Today")).toBeVisible();
  await page.getByRole("link", { name: "Trends" }).click();
  await expect(page.getByRole("heading", { name: "Use per day" })).toBeVisible();
});

test("a very long unbroken name doesn't overflow a phone", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 360, height: 740 } });
  const page = await context.newPage();
  await register(page);
  await page.getByRole("button", { name: "Something else" }).click();
  await page.getByLabel("Name").fill("W".repeat(60));
  await page.getByRole("button", { name: "Start tracking" }).click();
  await expect(page.getByRole("button", { name: "Log 1 time" })).toBeVisible();
  for (const path of ["/", "/trends", "/settings"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, path).toBeLessThanOrEqual(0);
  }
  await context.close();
});

test("nicotine pouches count in mg, with a daily mg limit", async ({ page }) => {
  await register(page);
  await page.getByRole("button", { name: "Nicotine pouches" }).click();
  await expect(page.getByLabel("Count it in")).toHaveValue("mg");
  await expect(page.getByLabel("Each log counts as (mg)")).toHaveValue("6");
  await page.getByLabel("Daily limit (mg)").fill("12");
  await page.getByRole("button", { name: "Start tracking" }).click();

  await page.getByRole("button", { name: "Log 6 mg" }).click();
  await expect(page.getByText("6 of 12 mg today")).toBeVisible();

  // A different strength is a one-off change to that log.
  await page.getByRole("button", { name: "Add details" }).click();
  await page.getByRole("dialog").getByLabel("Amount (mg)").fill("3");
  await page.getByRole("dialog").getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("3 of 12 mg today")).toBeVisible();
});

test("changing the unit on another preset updates the limit label", async ({ page }) => {
  await register(page);
  await page.getByRole("button", { name: "Alcohol" }).click();
  await page.getByLabel("Count it in").fill("ml");
  await expect(page.getByLabel("Daily limit (ml)")).toBeVisible();
});

async function addZyn(page: Page) {
  await page.getByRole("button", { name: "Nicotine pouches" }).click();
  await page.getByLabel("Name").fill("Zyn");
  await page.getByLabel("Daily limit (mg)").fill("90");
  await page.getByRole("button", { name: "Start tracking" }).click();
  await expect(page.getByText("Zyn").first()).toBeVisible();
}

test("levels: set up a plan, clear a level, step down, and the past stays as it was", async ({ page }) => {
  await register(page);
  await addZyn(page);
  await page.goto("/settings");
  await page.getByRole("button", { name: "Set up levels" }).click();
  await expect(page.getByText("16 levels.")).toBeVisible();
  await page.getByRole("button", { name: "Save levels" }).click();
  await expect(page.getByText("Levels on: down 6 mg after 7 days cleared")).toBeVisible();

  await page.goto("/");
  await expect(page.getByText("Level 1 of 16, 0 of 7 days cleared")).toBeVisible();
  // Nothing is offered until the level is cleared.
  await expect(page.getByRole("button", { name: /Step down/ })).toBeHidden();

  // Moves the tracker back eight days with each confirmed, as clearing a level takes a week.
  const db = new DatabaseSync(process.env.TALLY_E2E_DB!);
  db.exec(`
    UPDATE trackers SET created_at = datetime('now', '-9 days'), plan_started_on = date('now', '-8 days');
    UPDATE limit_periods SET starts_on = date('now', '-8 days');
  `);
  const insert = db.prepare("INSERT OR IGNORE INTO no_use_days SELECT id, date('now', ?) FROM trackers");
  for (let days = 1; days <= 8; days++) insert.run(`-${days} days`);
  db.close();

  await page.reload();
  await page.getByRole("button", { name: "Level cleared. Step down to 84 mg a day" }).click();
  await expect(page.getByText("Your limit is 84 mg a day from today")).toBeVisible();
  await page.reload();
  await expect(page.getByText("0 of 84 mg today")).toBeVisible();
  await expect(page.getByText("Level 2 of 16")).toBeVisible();

  await page.getByRole("link", { name: "Trends" }).click();
  await expect(page.getByRole("heading", { name: "Level 2 of 16" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your records" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Milestones" })).toBeVisible();
});

test("levels aren't offered where tapering needs a clinician", async ({ page }) => {
  await register(page);
  await addAlcohol(page);
  await page.goto("/settings");
  await expect(page.getByRole("button", { name: "Edit" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Set up levels" })).toBeHidden();
});

test("logging keeps working with no signal, and sends once when back", async ({ browser }) => {
  const context = await browser.newContext({ serviceWorkers: "allow" });
  const page = await context.newPage();
  await register(page);
  await addZyn(page);
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Zyn" })).toBeVisible();
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
  // One log online, so its assets and today's copy are saved.
  await page.getByRole("button", { name: "Log 6 mg" }).click();
  await expect(page.getByText("6 of 90 mg today")).toBeVisible();
  await page.waitForLoadState("networkidle");

  await context.setOffline(true);
  await page.getByRole("button", { name: "Log 6 mg" }).click();
  await expect(page.getByText("Saved on this device")).toBeVisible();
  await expect(page.getByText("12 of 90 mg today")).toBeVisible();
  await expect(page.getByText("1 log waiting to send")).toBeVisible();

  // A reload with no signal still opens the app, with the count intact.
  await page.reload();
  await expect(page.getByText("12 of 90 mg today")).toBeVisible();
  await page.getByRole("button", { name: "Log 6 mg" }).click();
  await expect(page.getByText("18 of 90 mg today")).toBeVisible();
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByText("12 of 90 mg today")).toBeVisible();

  await context.setOffline(false);
  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  await expect(page.getByText("waiting to send")).toBeHidden();
  await page.reload();
  await expect(page.getByText("12 of 90 mg today")).toBeVisible();
  const entries = await page.evaluate(() => fetch("/api/entries").then((r) => r.json()));
  expect(entries).toHaveLength(2);

  // Logging out removes what's stored on the device.
  await page.goto("/settings");
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  const left = await page.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith("tally.")));
  expect(left).toEqual([]);
  await context.close();
});

test("a lost reply can't double count, because a resend is recognised", async ({ page }) => {
  await register(page);
  await addZyn(page);
  // The server gets the first attempt, but its reply never arrives.
  await page.route("**/api/entries", async (route) => {
    await route.fetch();
    await route.abort("connectionreset");
  }, { times: 1 });
  await page.getByRole("button", { name: "Log 6 mg" }).click();
  await expect(page.getByText("Saved on this device")).toBeVisible();
  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  await expect(page.getByText("waiting to send")).toBeHidden();
  await page.reload();
  await expect(page.getByText("6 of 90 mg today")).toBeVisible();
});

test("a blank day earns nothing until it's confirmed", async ({ page }) => {
  await register(page);
  await addZyn(page);
  const db = new DatabaseSync(process.env.TALLY_E2E_DB!);
  db.exec("UPDATE trackers SET created_at = datetime('now', '-3 days')");
  db.close();
  await page.reload();
  await expect(page.getByText("has no logs.").first()).toBeVisible();
  await page.getByRole("button", { name: "Yes, no use" }).click();
  await expect(page.getByText("saved as a day without use")).toBeVisible();
});

test("a Wi-Fi login page answering for the server doesn't lose a waiting log", async ({ page }) => {
  await register(page);
  await addZyn(page);
  await page.route("**/api/entries", (route) =>
    route.fulfill({ status: 200, contentType: "text/html", body: "<h1>Sign in to Wi-Fi</h1>" }),
  );
  await page.getByRole("button", { name: "Log 6 mg" }).click();
  await expect(page.getByText("Saved on this device")).toBeVisible();
  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  await expect(page.getByText("1 log waiting to send")).toBeVisible();
  await page.unroute("**/api/entries");
  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  await expect(page.getByText("waiting to send")).toBeHidden();
  await page.reload();
  await expect(page.getByText("6 of 90 mg today")).toBeVisible();
});

test("a log tapped as the session expires is sent after logging back in", async ({ page }) => {
  const name = await register(page);
  await addZyn(page);
  await page.context().clearCookies();
  await page.getByRole("button", { name: "Log 6 mg" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("Username").fill(name);
  await page.getByLabel("Passphrase").fill(PASSPHRASE);
  await page.getByRole("button", { name: "Log in", exact: true }).click();
  await expect(page.getByText("6 of 90 mg today")).toBeVisible();
  await page.reload();
  await expect(page.getByText("6 of 90 mg today")).toBeVisible();
});

test("closing the app while a log is sending doesn't lose it", async ({ page }) => {
  await register(page);
  await addZyn(page);
  // The request never reaches the server before the page goes away.
  await page.route("**/api/entries", () => {}, { times: 1 });
  await page.getByRole("button", { name: "Log 6 mg" }).click();
  await expect(page.getByText("6 of 90 mg today")).toBeVisible();
  await page.reload();
  await expect(page.getByText("6 of 90 mg today")).toBeVisible();
  await page.reload();
  await expect(page.getByText("6 of 90 mg today")).toBeVisible();
  const entries = await page.evaluate(() => fetch("/api/entries").then((r) => r.json()));
  expect(entries).toHaveLength(1);
});

test("undo after a lost reply really removes the log", async ({ page }) => {
  await register(page);
  await addZyn(page);
  await page.route("**/api/entries", async (route) => {
    await route.fetch();
    await route.abort("connectionreset");
  }, { times: 1 });
  await page.getByRole("button", { name: "Log 6 mg" }).click();
  await expect(page.getByText("Saved on this device")).toBeVisible();
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByText("0 of 90 mg today")).toBeVisible();
  await page.reload();
  await expect(page.getByText("0 of 90 mg today")).toBeVisible();
});

test("exports download and contain my data", async ({ page }) => {
  await register(page);
  await addAlcohol(page);
  await page.getByRole("button", { name: "Log 1 drink" }).click();
  await expect(page.getByText("1 of 2 drinks today")).toBeVisible();
  await page.goto("/settings");
  const [csv] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "Download as CSV" }).click(),
  ]);
  expect(csv.suggestedFilename()).toBe("tally-export.csv");
});

test("settings: hide, restore, delete tracker, log out and back in, delete account", async ({ page }) => {
  const name = await register(page);
  await addAlcohol(page);
  await page.goto("/settings");

  await page.getByRole("button", { name: "Hide" }).click();
  await expect(page.getByText("Hidden from Today")).toBeVisible();
  await page.getByRole("button", { name: "Show on Today" }).click();
  await expect(page.getByText("Cut back, limit 2 drinks a day")).toBeVisible();

  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("Username").fill(name);
  await page.getByLabel("Passphrase").fill("wrong passphrase");
  await page.getByRole("button", { name: "Log in", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("incorrect");
  await page.getByLabel("Passphrase").fill(PASSPHRASE);
  await page.getByRole("button", { name: "Log in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Alcohol" })).toBeVisible();

  await page.goto("/settings");
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await page.getByRole("button", { name: "Delete Alcohol and its history" }).click();
  await expect(page.locator(".tracker-list li")).toHaveCount(0);

  await page.getByText("Delete account").click();
  await page.getByLabel("Enter your passphrase to confirm").fill(PASSPHRASE);
  await page.getByRole("button", { name: "Delete my account and all logs" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("Username").fill(name);
  await page.getByLabel("Passphrase").fill(PASSPHRASE);
  await page.getByRole("button", { name: "Log in", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("incorrect");
});

for (const colorScheme of ["light", "dark"] as const) {
  test(`no accessibility violations or overflow on a phone, ${colorScheme}`, async ({ browser }) => {
    const context = await browser.newContext({ colorScheme, viewport: { width: 360, height: 740 } });
    const page = await context.newPage();
    await register(page);
    await addAlcohol(page);
    for (let i = 0; i < 3; i++) await page.getByRole("button", { name: "Log 1 drink" }).click();
    await page.getByRole("button", { name: "Had an urge, didn't use" }).click();
    await expect(page.getByText("1 urge without use")).toBeVisible();
    await page.getByRole("button", { name: "Add details" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Stress" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("dialog")).toBeHidden();

    await page.goto("/settings");
    await page.getByRole("button", { name: "Add something to track" }).click();
    await addZyn(page);
    await page.goto("/settings");
    await page.getByRole("button", { name: "Set up levels" }).click();
    await page.getByRole("button", { name: "Save levels" }).click();
    await expect(page.getByText("Levels on:")).toBeVisible();

    for (const path of ["/", "/trends", "/history", "/settings", "/help"]) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      if (path === "/trends") {
        await page.getByRole("button", { name: "Zyn" }).click();
        await expect(page.locator(".level-panel")).toBeVisible();
      }
      if (path === "/trends") await page.getByRole("button", { name: "Zyn" }).click();
      if (path === "/trends") await expect(page.locator(".level-panel")).toBeVisible();
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
      expect(results.violations.map((v) => `${path}: ${v.id} ${v.nodes[0].html}`)).toEqual([]);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, path).toBeLessThanOrEqual(0);
    }
    await context.close();
  });
}
