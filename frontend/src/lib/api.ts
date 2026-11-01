export type Goal = "quit" | "reduce" | "manage" | "observe";
export type Category =
  | "alcohol" | "nicotine" | "cannabis" | "opioid" | "benzodiazepine"
  | "stimulant" | "caffeine" | "gambling" | "behavior" | "other";

export interface Tracker {
  id: number;
  name: string;
  category: Category;
  goal: Goal;
  unit: string;
  default_amount: number;
  daily_limit: number | null;
  created_at: string;
  archived_at: string | null;
}

export interface TodayTracker extends Tracker {
  uses_today: number;
  amount_today: number;
  urges_today: number;
  last_use_at: string | null;
}

export interface Entry {
  id: number;
  tracker_id: number;
  kind: "use" | "urge";
  occurred_at: string;
  amount: number | null;
  craving: number | null;
  trigger: string | null;
  note: string | null;
}

export interface DayStat {
  date: string;
  amount: number;
  uses: number;
  urges: number;
  average_7d: number;
}

export interface Stats {
  window_start: string;
  daily: DayStat[];
  heatmap: number[][];
  triggers: { trigger: string; uses: number; urges: number }[];
  summary: {
    amount_in_window: number;
    uses_in_window: number;
    urges_in_window: number;
    average_craving: number | null;
    recent_7: number | null;
    previous_7: number | null;
    change_pct: number | null;
    within_goal: { days: number; of: number; limit: number } | null;
    last_use_at: string | null;
    longest_gap_hours: number | null;
  };
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

let onUnauthorized = () => {};
export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler;
}

export const timeZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

function errorMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0]?.msg) {
    const field = detail[0].loc?.at(-1);
    const message = String(detail[0].msg).replace(/^Value error, /, "");
    return field ? `${field}: ${message}` : message;
  }
  return "That didn't work. Check your connection and try again.";
}

export async function api<T = void>(path: string, method = "GET", body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      credentials: "same-origin",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your connection and try again.");
  }
  if (!res.ok) {
    const payload = await res.json().catch(() => ({}));
    if (res.status === 401 && !path.startsWith("/api/auth/login")) onUnauthorized();
    throw new ApiError(res.status, errorMessage(payload.detail));
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}
