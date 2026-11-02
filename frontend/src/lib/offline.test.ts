import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Entry, Stopped, TodayTracker } from "./api";
import { addToCachedToday, advanceStopped, cachedToday, enqueue } from "./offline";

const saved: Stopped = { since: "2025-09-20", days_free: 100, current_days: 100, longest_days: 100, days_with_use: 0, urges: 0 };

describe("a saved Today from an earlier day", () => {
  it("moves on by the days since it was saved", () => {
    expect(advanceStopped(saved, "2026-01-01", "2026-01-04", [])).toMatchObject({ days_free: 103, current_days: 103, longest_days: 103 });
  });

  it("doesn't count the saved day if it had a use, or count that use twice", () => {
    const counted = { ...saved, current_days: 0, days_with_use: 1 };
    expect(advanceStopped(counted, "2026-01-01", "2026-01-04", [], true)).toMatchObject({ days_free: 102, current_days: 2, longest_days: 100, days_with_use: 1 });
  });

  it("doesn't award a later day that has a use still waiting to send", () => {
    expect(advanceStopped(saved, "2026-01-01", "2026-01-05", ["2026-01-02", "2026-01-02"])).toMatchObject({ days_free: 103, current_days: 2, longest_days: 101, days_with_use: 1 });
  });

  it("counts nothing up to the last-use date", () => {
    expect(advanceStopped({ ...saved, since: "2026-01-02" }, "2026-01-01", "2026-01-04", [])).toMatchObject({ days_free: 101 });
  });
});

describe("the saved copy on this device", () => {
  const tracker = (uses_today: number, stopped: Stopped) =>
    ({ id: 1, default_amount: 1, uses_today, amount_today: uses_today, urges_today: 0, last_use_at: null, game: { stopped } }) as unknown as TodayTracker;
  const save = (day: string, trackers: TodayTracker[]) =>
    localStorage.setItem("tally.today.null", JSON.stringify({ day, trackers }));
  const stoppedNow = () => cachedToday()![0]!.game.stopped!;

  beforeEach(() => {
    const store = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => void store.set(key, value),
      removeItem: (key: string) => void store.delete(key),
    });
    vi.useFakeTimers({ now: new Date(2026, 0, 4, 12) });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("keeps the server's count when a day with a use rolls over", () => {
    save("2026-01-03", [tracker(1, { ...saved, current_days: 0, days_with_use: 1 })]);
    expect(stoppedNow()).toMatchObject({ days_with_use: 1, days_free: 100, current_days: 0 });
  });

  it("counts a use that got through when the refresh after it failed", () => {
    save("2026-01-04", [tracker(0, saved)]);
    const use = { tracker_id: 1, kind: "use", amount: 1, occurred_at: "2026-01-04T12:00:00Z" } as Entry;
    addToCachedToday(use);
    addToCachedToday(use);
    expect(stoppedNow()).toMatchObject({ days_with_use: 1, current_days: 0, days_free: 100 });
  });

  it("holds back a day whose use is still waiting to send", () => {
    save("2026-01-01", [tracker(0, saved)]);
    enqueue({ client_id: "abcdefgh", tracker_id: 1, kind: "use", occurred_at: new Date(2026, 0, 2, 12).toISOString() });
    expect(stoppedNow()).toMatchObject({ days_free: 102, current_days: 1, days_with_use: 1 });
  });

  it("ignores a queued use that was undone", () => {
    save("2026-01-01", [tracker(0, saved)]);
    enqueue({ client_id: "abcdefgh", tracker_id: 1, kind: "use", occurred_at: new Date(2026, 0, 2, 12).toISOString(), cancelled: true });
    expect(stoppedNow()).toMatchObject({ days_free: 103, days_with_use: 0 });
  });
});
