import { describe, expect, it } from "vitest";
import { advanceStopped } from "./offline";

const saved = { since: "2025-09-20", days_free: 100, current_days: 100, longest_days: 100, days_with_use: 0, urges: 0 };

describe("a saved Today from an earlier day", () => {
  it("moves on by the days since it was saved", () => {
    expect(advanceStopped(saved, 3, false)).toMatchObject({ days_free: 103, current_days: 103, longest_days: 103 });
  });

  it("doesn't count the saved day if it had a use", () => {
    expect(advanceStopped(saved, 3, true)).toMatchObject({ days_free: 102, current_days: 2, longest_days: 100, days_with_use: 1 });
  });
});
