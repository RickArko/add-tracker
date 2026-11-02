import type { Drink } from "./api";

const ETHANOL_G_PER_ML = 0.789;
const STANDARD_DRINK_G = 14;

/** An estimate, to the nearest 0.1 and never zero. app/stats.py does the same steps in the same order. */
export function standardDrinks(servings: number, servingMl: number, abv: number): number {
  const exact = ((((servings * servingMl * abv) / 100) * ETHANOL_G_PER_ML) / STANDARD_DRINK_G);
  return Math.max(0.1, Math.floor(exact * 10 + 0.5) / 10);
}

export const drinkAmount = (drink: Drink) => standardDrinks(drink.servings, drink.serving_ml, drink.abv);

export function drinkLabel(name: string, servings: number): string {
  return servings === 1 ? name : `${servings} × ${name}`;
}

export interface DrinkType {
  name: string;
  /** Typical strength, and always editable because real drinks vary. */
  abv: number;
  sizes: { label: string; ml: number }[];
}

const BEER_SIZES = [
  { label: "12 oz", ml: 355 },
  { label: "16 oz pint", ml: 473 },
  { label: "20 oz pint", ml: 568 },
];
const WINE_SIZES = [
  { label: "5 oz glass", ml: 148 },
  { label: "8 oz glass", ml: 237 },
];

export const DRINK_TYPES: DrinkType[] = [
  { name: "Beer", abv: 5, sizes: BEER_SIZES },
  { name: "Light beer", abv: 4.2, sizes: BEER_SIZES },
  { name: "IPA", abv: 6.5, sizes: BEER_SIZES },
  { name: "Hard seltzer", abv: 5, sizes: BEER_SIZES.slice(0, 2) },
  { name: "Wine", abv: 13, sizes: WINE_SIZES },
  { name: "Champagne", abv: 12, sizes: [{ label: "Flute", ml: 150 }, ...WINE_SIZES.slice(0, 1)] },
  { name: "Spirits", abv: 40, sizes: [{ label: "1.5 oz shot", ml: 44 }, { label: "Double", ml: 88 }] },
];
