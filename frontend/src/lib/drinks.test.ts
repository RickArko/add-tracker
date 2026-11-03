import { describe, expect, it } from "vitest";
import { DRINK_TYPES, standardDrinks } from "./drinks";

describe("standard drinks", () => {
  // tests/test_drinks.py checks the same figures.
  it.each([
    [1, 355, 5, 1.0],
    [3, 355, 6.5, 3.9],
    [2, 150, 12, 2.0],
    [1, 148, 12, 1.0],
    [1, 44, 40, 1.0],
    [1, 355, 0.5, 0.1],
    [1, 10, 0.1, 0.1],
    [1, 700, 100, 39.5],
  ])("%i x %i ml at %f%% is %f", (servings, ml, abv, expected) => {
    expect(standardDrinks(servings, ml, abv)).toBe(expected);
  });

  it("offers at least one size for every type", () => {
    for (const type of DRINK_TYPES) expect(type.sizes.length).toBeGreaterThan(0);
  });
});
