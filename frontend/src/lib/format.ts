const NO_PLURAL = new Set(["mg", "g", "kg", "mcg", "ug", "ml", "l", "oz", "lb", "puffs", "$", "min", "hr"]);

/** Whole numbers stay whole; anything else shows at most two decimals. */
export function formatNumber(value: number): string {
  return String(Math.round(value * 100) / 100);
}

export function unitLabel(unit: string, amount: number): string {
  if (amount === 1 || NO_PLURAL.has(unit.toLowerCase()) || /s$/i.test(unit)) return unit;
  return /(ch|sh|x|z)$/i.test(unit) ? `${unit}es` : `${unit}s`;
}

export function quantity(amount: number, unit: string): string {
  return `${formatNumber(amount)} ${unitLabel(unit, amount)}`;
}

export function duration(hours: number): string {
  if (hours < 1) {
    const minutes = Math.floor(hours * 60);
    return minutes < 1 ? "under a minute" : `${minutes} ${minutes === 1 ? "minute" : "minutes"}`;
  }
  if (hours < 48) {
    const whole = Math.floor(hours);
    return `${whole} ${whole === 1 ? "hour" : "hours"}`;
  }
  return `${Math.floor(hours / 24)} days`;
}

export function timeSince(iso: string, now: Date = new Date()): string {
  const hours = Math.max(0, now.getTime() - new Date(iso).getTime()) / 3_600_000;
  return duration(hours);
}

/** Parses YYYY-MM-DD as a local date, since `new Date(string)` would read it as UTC. */
export function localDate(isoDate: string): Date {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(year, month - 1, day);
}

export function shortDate(isoDate: string): string {
  return localDate(isoDate).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function longDate(date: Date): string {
  return date.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
}

export function clockTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

/** The value a datetime-local input expects, in the device's own time zone. */
export function toLocalInput(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

export function changeSentence(pct: number | null): string {
  if (pct === null) return "";
  if (pct === 0) return "the same as the week before";
  return `${pct < 0 ? "down" : "up"} ${Math.abs(pct)}% from the week before`;
}

/** Tally positions are grouped in fives: four uprights, then a strike across them. */
export function tallyGroups(count: number): number[] {
  const groups = Array<number>(Math.floor(count / 5)).fill(5);
  if (count % 5) groups.push(count % 5);
  return groups;
}

/** A round axis maximum that sits at or just above the largest value. */
export function niceMax(value: number): number {
  if (value <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  const scaled = value / power;
  const step = [1, 1.5, 2, 3, 4, 5, 6, 8, 10].find((s) => scaled <= s) ?? 10;
  return step * power;
}
