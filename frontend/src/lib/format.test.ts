import { describe, expect, it } from "vitest";
import {
  changeSentence, dayCount, duration, formatNumber, fullDate, localDate, niceMax, quantity,
  tallyGroups, timeSince, toLocalInput, unitLabel, yesterday,
} from "./format";

describe("units", () => {
  it("pluralises words and leaves measures alone", () => {
    expect(unitLabel("drink", 1)).toBe("drink");
    expect(unitLabel("drink", 2)).toBe("drinks");
    expect(unitLabel("drink", 0)).toBe("drinks");
    expect(unitLabel("mg", 20)).toBe("mg");
    expect(unitLabel("puffs", 2)).toBe("puffs");
    expect(unitLabel("pouch", 2)).toBe("pouches");
  });
  it("formats quantities without float noise", () => {
    expect(formatNumber(0.1 + 0.2)).toBe("0.3");
    expect(quantity(2.5, "drink")).toBe("2.5 drinks");
    expect(quantity(1, "cup")).toBe("1 cup");
  });
});

describe("time", () => {
  it("rounds durations down to readable units", () => {
    expect(duration(0)).toBe("under a minute");
    expect(duration(1 / 60)).toBe("1 minute");
    expect(duration(1)).toBe("1 hour");
    expect(duration(47.9)).toBe("47 hours");
    expect(duration(72)).toBe("3 days");
  });
  it("never reports a negative time since", () => {
    const now = new Date("2026-01-01T00:00:00Z");
    expect(timeSince("2026-01-01T01:00:00Z", now)).toBe("under a minute");
  });
  it("reads calendar dates as local, not UTC", () => {
    const date = localDate("2026-03-01");
    expect([date.getFullYear(), date.getMonth(), date.getDate()]).toEqual([2026, 2, 1]);
  });
  it("round-trips through a datetime-local value", () => {
    const date = new Date(2026, 0, 5, 7, 9);
    expect(toLocalInput(date)).toBe("2026-01-05T07:09");
    expect(new Date(toLocalInput(date)).getTime()).toBe(date.getTime());
  });
});

describe("trend wording", () => {
  it("states direction plainly", () => {
    expect(changeSentence(-12)).toBe("down 12% from the week before");
    expect(changeSentence(8)).toBe("up 8% from the week before");
    expect(changeSentence(0)).toBe("the same as the week before");
    expect(changeSentence(null)).toBe("");
  });
});

describe("tally groups", () => {
  it("bundles in fives", () => {
    expect(tallyGroups(0)).toEqual([]);
    expect(tallyGroups(4)).toEqual([4]);
    expect(tallyGroups(5)).toEqual([5]);
    expect(tallyGroups(12)).toEqual([5, 5, 2]);
  });
});

describe("niceMax", () => {
  it("stays at or above the value", () => {
    for (const value of [0.3, 1, 3, 4.2, 7, 11, 26, 99, 1000]) {
      expect(niceMax(value)).toBeGreaterThanOrEqual(value);
    }
    expect(niceMax(0)).toBe(1);
    expect(niceMax(4.2)).toBe(5);
  });
});

describe("already stopped helpers", () => {
  it("counts days in the right grammar", () => {
    expect(dayCount(0)).toBe("0 days");
    expect(dayCount(1)).toBe("1 day");
    expect(dayCount(407)).toBe("407 days");
  });

  it("finds the previous local day across a month and a year", () => {
    expect(yesterday(new Date(2026, 10, 1, 0, 30))).toBe("2026-10-31");
    expect(yesterday(new Date(2026, 0, 1, 23, 30))).toBe("2025-12-31");
  });

  it("keeps the year in a full date", () => {
    expect(fullDate("2025-09-20")).toContain("2025");
  });
});
