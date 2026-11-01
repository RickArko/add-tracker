import { api, ApiError, type Entry, type Stopped, type TodayTracker } from "./api";
import { auth } from "./auth";

/**
 * Lets logging work with no signal. A log the server didn't get waits here with the time it was
 * tapped, and its client id means resending can't count it twice. Everything is removed on log out.
 */
export interface QueuedLog {
  client_id: string;
  tracker_id: number;
  kind: "use" | "urge";
  occurred_at: string;
  /** Undone while its fate was unknown, so the server copy must go if it arrived. */
  cancelled?: boolean;
}

const queueKey = (username: string | null = auth.username) => `tally.queue.${username}`;
const todayKey = () => `tally.today.${auth.username}`;

function read<T>(key: string, fallback: T): T {
  try {
    return (JSON.parse(localStorage.getItem(key) ?? "null") as T | null) ?? fallback;
  } catch {
    return fallback;
  }
}

export const getQueue = () => read<QueuedLog[]>(queueKey(), []);

/** Logs still to be counted, which leaves out any being cancelled. */
export const waitingLogs = () => getQueue().filter((log) => !log.cancelled);

/** Saved before sending, so a closed app or a dropped connection can't lose the tap. */
export function enqueue(log: QueuedLog) {
  localStorage.setItem(queueKey(), JSON.stringify([...getQueue(), log]));
}

export function removeFromQueue(clientId: string, username: string | null = auth.username) {
  const key = queueKey(username);
  const queue = read<QueuedLog[]>(key, []);
  localStorage.setItem(key, JSON.stringify(queue.filter((log) => log.client_id !== clientId)));
}

export function cancelQueued(clientId: string) {
  localStorage.setItem(
    queueKey(),
    JSON.stringify(
      getQueue().map((log) => (log.client_id === clientId ? { ...log, cancelled: true } : log)),
    ),
  );
}

/**
 * Only a clear refusal from this server is final. Anything else, including a captive portal or
 * proxy answering in its place, may succeed later, and client ids make retrying safe.
 */
export function isRetryable(error: unknown): boolean {
  if (!(error instanceof ApiError)) return true;
  return !error.fromApp || error.status === 0 || error.status === 401 || error.status === 429 || error.status >= 500;
}

let flushing: Promise<number> | null = null;

/** Sends waiting logs in order, and returns how many were refused for good. */
export function flushQueue(): Promise<number> {
  flushing ??= (async () => {
    const owner = auth.username;
    let refused = 0;
    for (const log of read<QueuedLog[]>(queueKey(owner), [])) {
      try {
        if (log.cancelled) {
          await api(`/api/entries/by-client/${encodeURIComponent(log.client_id)}`, "DELETE");
        } else {
          const { cancelled: _cancelled, ...body } = log;
          await api<Entry>("/api/entries", "POST", body);
        }
      } catch (error) {
        if (isRetryable(error)) break;
        refused += 1;
      }
      removeFromQueue(log.client_id, owner);
    }
    return refused;
  })().finally(() => {
    flushing = null;
  });
  return flushing;
}

export function localDay(date: Date = new Date()): string {
  return date.toLocaleDateString("en-CA");
}

export function cacheToday(trackers: TodayTracker[]) {
  localStorage.setItem(todayKey(), JSON.stringify({ day: localDay(), trackers }));
}

/** Day counts from a saved copy, moved on by the days since it was saved. */
export function advanceStopped(stopped: Stopped, elapsed: number, usedThatDay: boolean): Stopped {
  // The saved day has now finished. It counts unless it had a use.
  const gained = Math.max(0, elapsed - (usedThatDay ? 1 : 0));
  const current = (usedThatDay ? 0 : stopped.current_days) + gained;
  return {
    ...stopped,
    days_free: stopped.days_free + gained,
    current_days: current,
    longest_days: Math.max(stopped.longest_days, current),
    days_with_use: stopped.days_with_use + (usedThatDay ? 1 : 0),
  };
}

/** The last known Today, with the counts zeroed if it's from an earlier day. */
export function cachedToday(): TodayTracker[] | null {
  const saved = read<{ day: string; trackers: TodayTracker[] } | null>(todayKey(), null);
  if (!saved) return null;
  if (saved.day === localDay()) return saved.trackers;
  const elapsed = Math.round((new Date(localDay()).getTime() - new Date(saved.day).getTime()) / 86_400_000);
  return saved.trackers.map((t) => ({
    ...t,
    game: { ...t.game, stopped: t.game.stopped && advanceStopped(t.game.stopped, elapsed, t.uses_today > 0) },
    uses_today: 0,
    amount_today: 0,
    urges_today: 0,
  }));
}

/** Keeps the saved copy current, so a reload with no signal still shows a log that got through. */
export function addToCachedToday(entry: Entry) {
  const trackers = cachedToday();
  const tracker = trackers?.find((t) => t.id === entry.tracker_id);
  if (!trackers || !tracker) return;
  if (entry.kind === "use") {
    tracker.uses_today += 1;
    tracker.amount_today += entry.amount ?? 0;
    tracker.last_use_at = entry.occurred_at;
  } else {
    tracker.urges_today += 1;
  }
  cacheToday(trackers);
}

/** Adds waiting logs from today onto a server or cached count. */
export function withQueue(trackers: TodayTracker[]): TodayTracker[] {
  const today = localDay();
  const copy = trackers.map((t) => ({ ...t }));
  for (const log of waitingLogs()) {
    const tracker = copy.find((t) => t.id === log.tracker_id);
    if (!tracker) continue;
    if (log.kind === "use") tracker.last_use_at = log.occurred_at;
    if (localDay(new Date(log.occurred_at)) !== today) continue;
    if (log.kind === "use") {
      tracker.uses_today += 1;
      tracker.amount_today += tracker.default_amount;
    } else {
      tracker.urges_today += 1;
    }
  }
  return copy;
}

/** Removes this user's data from the device. Another account's unsent logs stay put. */
export function clearLocalData() {
  localStorage.removeItem(queueKey());
  localStorage.removeItem(todayKey());
  localStorage.removeItem("tally.user");
}
