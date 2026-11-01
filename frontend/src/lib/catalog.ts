import type { Category, Goal } from "./api";

export interface Preset {
  label: string;
  name: string;
  category: Category;
  unit: string;
}

export const PRESETS: Preset[] = [
  { label: "Alcohol", name: "Alcohol", category: "alcohol", unit: "drink" },
  { label: "Nicotine", name: "Nicotine", category: "nicotine", unit: "use" },
  { label: "Cannabis", name: "Cannabis", category: "cannabis", unit: "session" },
  { label: "Caffeine", name: "Caffeine", category: "caffeine", unit: "cup" },
  { label: "Opioids", name: "Opioids", category: "opioid", unit: "dose" },
  { label: "Benzodiazepines", name: "Benzodiazepines", category: "benzodiazepine", unit: "dose" },
  { label: "Stimulants", name: "Stimulants", category: "stimulant", unit: "dose" },
  { label: "Gambling", name: "Gambling", category: "gambling", unit: "session" },
  { label: "Social media", name: "Social media", category: "behavior", unit: "session" },
  { label: "Something else", name: "", category: "other", unit: "time" },
];

export const GOALS: { value: Goal; label: string; hint: string }[] = [
  { value: "reduce", label: "Cut back", hint: "Use less over time" },
  { value: "quit", label: "Stop", hint: "Work toward none" },
  { value: "manage", label: "Stay within a limit", hint: "Keep use steady" },
  { value: "observe", label: "Just watch", hint: "See the pattern first" },
];

export const TRIGGERS = ["Stress", "Boredom", "Social", "Routine", "Tired", "Low mood", "Pain", "Celebrating"];

/** Shown when someone plans to stop or cut back on something with a dangerous withdrawal. */
export function safetyNote(category: Category, goal: Goal): string | null {
  if (goal !== "quit" && goal !== "reduce") return null;
  if (category === "alcohol" || category === "benzodiazepine") {
    return "If you use this daily or heavily, stopping suddenly can cause seizures and can be life-threatening. Talk to a clinician before you stop. They can help you taper safely.";
  }
  if (category === "opioid") {
    return "Tolerance drops quickly after cutting back, so a dose you used to take can become an overdose. Keep naloxone nearby and ask a clinician about medication, which greatly lowers risk.";
  }
  return null;
}

export function goalLabel(goal: Goal): string {
  return GOALS.find((g) => g.value === goal)?.label ?? goal;
}
