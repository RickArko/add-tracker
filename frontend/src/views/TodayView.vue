<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import EntryDialog from "../components/EntryDialog.vue";
import TallyMarks from "../components/TallyMarks.vue";
import TrackerForm from "../components/TrackerForm.vue";
import { api, ApiError, timeZone, type Entry, type TodayTracker, type Tracker } from "../lib/api";
import { dayCount, duration, formatNumber, fullDate, longDate, quantity, shortDate, timeSince, unitLabel } from "../lib/format";
import { safetyNote } from "../lib/catalog";
import {
  addToCachedToday, cachedToday, cacheToday, cancelQueued, enqueue, flushQueue, isRetryable,
  removeFromQueue, waitingLogs, withQueue,
} from "../lib/offline";

const trackers = ref<TodayTracker[]>([]);
const loaded = ref(false);
const loadError = ref("");
const waiting = ref(0);
const editing = ref<Entry | null>(null);
const toast = ref<{ text: string; entry?: Entry; queuedId?: string } | null>(null);
const today = ref(new Date());
let toastTimer: number | undefined;
// Logs still being sent. A reload during one would overwrite its optimistic count.
let pendingLogs = 0;
// Moves on with each load and each tap, so a reply that's been overtaken can be ignored.
let latestLoad = 0;
let loadsRunning = 0;
let reloadWhenSettled = false;

const editingTracker = computed(() =>
  trackers.value.find((t) => t.id === editing.value?.tracker_id),
);

async function load() {
  if (pendingLogs > 0) {
    reloadWhenSettled = true;
    return;
  }
  const thisLoad = ++latestLoad;
  loadsRunning += 1;
  today.value = new Date();
  try {
    const refused = await flushQueue();
    if (refused) showToast(`${refused} waiting ${refused === 1 ? "log was" : "logs were"} refused by the server, so check History.`);
    const fresh = await api<TodayTracker[]>(`/api/today?tz=${encodeURIComponent(timeZone())}`);
    if (thisLoad !== latestLoad) return;
    cacheToday(fresh);
    trackers.value = withQueue(fresh);
    loadError.value = "";
  } catch (e) {
    if (thisLoad !== latestLoad) return;
    const saved = isRetryable(e) ? cachedToday() : null;
    if (saved) {
      trackers.value = withQueue(saved);
      loadError.value = "";
    } else {
      loadError.value = e instanceof ApiError ? e.message : "Today's log didn't load.";
    }
  } finally {
    loadsRunning -= 1;
  }
  waiting.value = waitingLogs().length;
  loaded.value = true;
}

function showToast(text: string, extra: { entry?: Entry; queuedId?: string } = {}) {
  toast.value = { text, ...extra };
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => (toast.value = null), 8000);
}

function adjust(tracker: TodayTracker, kind: "use" | "urge", direction: 1 | -1) {
  if (kind === "use") {
    tracker.uses_today += direction;
    tracker.amount_today += direction * tracker.default_amount;
  } else {
    tracker.urges_today += direction;
  }
}

async function log(tracker: TodayTracker, kind: "use" | "urge") {
  pendingLogs += 1;
  // A load already running read the server before this tap, so its reply is out of date.
  latestLoad += 1;
  if (loadsRunning > 0) reloadWhenSettled = true;
  const clientId = crypto.randomUUID();
  const tappedAt = new Date().toISOString();
  enqueue({ client_id: clientId, tracker_id: tracker.id, kind, occurred_at: tappedAt });
  // Update first, so a tap feels instant even on a slow connection.
  adjust(tracker, kind, 1);
  try {
    const entry = await api<Entry>("/api/entries", "POST", {
      tracker_id: tracker.id,
      kind,
      client_id: clientId,
    });
    removeFromQueue(clientId);
    addToCachedToday(entry);
    showToast(
      kind === "use" ? `Logged ${quantity(entry.amount ?? 0, tracker.unit)}` : "Logged urge",
      { entry },
    );
    if (kind === "use") tracker.last_use_at = entry.occurred_at;
    // The day counts come from the server.
    if (tracker.game.stopped) reloadWhenSettled = true;
  } catch (e) {
    if (isRetryable(e)) {
      waiting.value = waitingLogs().length;
      if (kind === "use") tracker.last_use_at = tappedAt;
      showToast("Saved on this device. It'll send when you're back online.", { queuedId: clientId });
    } else {
      removeFromQueue(clientId);
      adjust(tracker, kind, -1);
      showToast(e instanceof ApiError ? e.message : "That didn't save. Try again.");
    }
  } finally {
    pendingLogs -= 1;
    if (pendingLogs === 0 && reloadWhenSettled) {
      reloadWhenSettled = false;
      void load();
    }
  }
}

async function undo(entry: Entry) {
  toast.value = null;
  try {
    await api(`/api/entries/${entry.id}`, "DELETE");
    showToast("Removed");
    await load();
  } catch (e) {
    showToast(e instanceof ApiError ? e.message : "That wasn't removed. Try again.");
  }
}

async function undoQueued(clientId: string) {
  toast.value = null;
  cancelQueued(clientId);
  showToast("Removed");
  await load();
}

function openDetails(entry: Entry) {
  toast.value = null;
  editing.value = entry;
}

async function afterEdit(text: string) {
  editing.value = null;
  showToast(text);
  await load();
}

async function created(_tracker: Tracker) {
  await load();
}

const steppingDown = ref(false);
const dismissedDays = ref<string[]>([]);

function blankDay(t: TodayTracker): string | null {
  return t.game.unlogged_recent.find((day) => !dismissedDays.value.includes(`${t.id}:${day}`)) ?? null;
}

async function confirmNoUse(t: TodayTracker, day: string) {
  try {
    await api(
      `/api/trackers/${t.id}/no-use-days?tz=${encodeURIComponent(timeZone())}`,
      "POST",
      { day },
    );
    showToast(`${shortDate(day)} saved as a day without use`);
    await load();
  } catch (e) {
    showToast(e instanceof ApiError ? e.message : "That didn't save. Try again.");
  }
}

async function stepDown(tracker: TodayTracker) {
  if (steppingDown.value) return;
  steppingDown.value = true;
  try {
    const updated = await api<Tracker>(
      `/api/trackers/${tracker.id}/step-down?tz=${encodeURIComponent(timeZone())}`,
      "POST",
    );
    showToast(
      updated.daily_limit === null
        ? "Final level. Your goal is now zero."
        : `New level. Your limit is ${quantity(updated.daily_limit, tracker.unit)} a day from today.`,
    );
    await load();
  } catch (e) {
    showToast(e instanceof ApiError ? e.message : "That didn't save. Try again.");
  } finally {
    steppingDown.value = false;
  }
}

/** A use today shows at once, even if the server hasn't seen it yet. */
function stoppedDays(t: TodayTracker) {
  const s = t.game.stopped!;
  return {
    free: s.days_free,
    current: t.uses_today > 0 ? 0 : s.current_days,
    hadUse: t.uses_today > 0 || s.days_with_use > 0,
  };
}

function limitNote(t: TodayTracker): string {
  if (t.daily_limit === null) return `${quantity(t.amount_today, t.unit)} today`;
  return `${formatNumber(t.amount_today)} of ${quantity(t.daily_limit, t.unit)} today`;
}

const onVisible = () => {
  if (document.visibilityState === "visible") void load();
};
const onOnline = () => void load();
onMounted(() => {
  void load();
  document.addEventListener("visibilitychange", onVisible);
  window.addEventListener("online", onOnline);
});
onBeforeUnmount(() => {
  document.removeEventListener("visibilitychange", onVisible);
  window.removeEventListener("online", onOnline);
  window.clearTimeout(toastTimer);
});
</script>

<template>
  <div class="page">
    <h1 class="date">{{ longDate(today) }}</h1>

    <p v-if="loadError" class="error" role="alert">
      {{ loadError }} <button class="link" type="button" @click="load">Try again</button>
    </p>
    <p v-if="waiting" class="waiting" role="status">
      {{ waiting }} {{ waiting === 1 ? "log" : "logs" }} waiting to send
    </p>

    <section v-if="loaded && !trackers.length && !loadError" class="first-run">
      <p class="lede">Log each time with one tap, and a pattern starts to show within days. Everything stays in your account.</p>
      <TrackerForm @saved="created" />
    </section>

    <ul class="today-list">
      <li v-for="t in trackers" :key="t.id" class="today-row" :data-tracker="t.name">
        <h2>{{ t.name }}</h2>
        <template v-if="t.game.stopped">
          <p class="stopped-days">{{ dayCount(stoppedDays(t).free) }} without use</p>
          <p class="today-facts">
            <span>Since you stopped on {{ fullDate(t.game.stopped.since) }}</span>
            <span v-if="stoppedDays(t).hadUse">Current stretch: {{ dayCount(stoppedDays(t).current) }}. Longest: {{ dayCount(t.game.stopped.longest_days) }}</span>
            <span v-if="t.urges_today">{{ t.urges_today }} {{ t.urges_today === 1 ? "urge" : "urges" }} without use today</span>
          </p>
          <p v-if="t.uses_today && safetyNote(t.category)" class="safety" role="note">
            {{ safetyNote(t.category) }} <RouterLink to="/help">Find support</RouterLink>
          </p>
          <div class="stopped-actions">
            <button class="log-urge" type="button" @click="log(t, 'urge')">Had an urge, didn't use</button>
            <button class="quiet" type="button" @click="log(t, 'use')">Log a use</button>
          </div>
        </template>
        <template v-else>
        <p class="tally-line">
          <TallyMarks v-if="t.uses_today" :count="t.uses_today" />
          <span v-else class="none-yet">No logs yet today</span>
        </p>
        <p class="today-facts">
          <span class="today-total">{{ limitNote(t) }}</span>
          <span v-if="t.urges_today">{{ t.urges_today }} {{ t.urges_today === 1 ? "urge" : "urges" }} without use</span>
          <span v-if="t.last_use_at">Last logged {{ timeSince(t.last_use_at) }} ago<template v-if="t.game.typical_gap_hours !== null">. Typical gap this week: {{ duration(t.game.typical_gap_hours) }}</template></span>
          <span v-if="t.game.level && !t.game.level.at_zero">
            Level {{ t.game.level.level }} of {{ t.game.level.total_levels }}, {{ Math.min(t.game.level.days_cleared, t.game.level.clear_days) }} of {{ t.game.level.clear_days }} days cleared
          </span>
          <span v-else-if="t.game.level">
            Level {{ t.game.level.level }} of {{ t.game.level.total_levels }}, {{ t.game.level.days_cleared }} {{ t.game.level.days_cleared === 1 ? "day" : "days" }} at zero
          </span>
        </p>
        <button
          v-if="t.game.level?.ready && t.game.level.next_limit !== null"
          type="button"
          class="step-down"
          :disabled="steppingDown"
          @click="stepDown(t)"
        >
          Level cleared. Step down to {{ quantity(t.game.level.next_limit, t.unit) }} a day
        </button>
        <div v-if="blankDay(t)" class="blank-day">
          <p>{{ shortDate(blankDay(t)!) }} has no logs. Blank days don't count toward progress. Was it a day without use?</p>
          <div class="actions">
            <button type="button" class="secondary" @click="confirmNoUse(t, blankDay(t)!)">Yes, no use</button>
            <button type="button" class="quiet" @click="dismissedDays.push(`${t.id}:${blankDay(t)}`)">No, leave it blank</button>
          </div>
        </div>
        <div class="log-actions">
          <button class="log-use" type="button" @click="log(t, 'use')">
            Log {{ formatNumber(t.default_amount) }} {{ unitLabel(t.unit, t.default_amount) }}
          </button>
          <button class="log-urge" type="button" @click="log(t, 'urge')">Had an urge, didn't use</button>
        </div>
        </template>
      </li>
    </ul>

    <p v-if="trackers.length" class="footer-links">
      <RouterLink to="/settings">Add or change what you track</RouterLink>
      <RouterLink to="/help">Get support</RouterLink>
    </p>

    <div v-if="toast" class="toast" role="status">
      <span>{{ toast.text }}</span>
      <template v-if="toast.entry">
        <button type="button" class="link" @click="openDetails(toast.entry)">Add details</button>
        <button type="button" class="link" @click="undo(toast.entry)">Undo</button>
      </template>
      <button v-else-if="toast.queuedId" type="button" class="link" @click="undoQueued(toast.queuedId!)">Undo</button>
    </div>

    <EntryDialog
      v-if="editing"
      :entry="editing"
      :tracker="editingTracker"
      @close="editing = null"
      @saved="afterEdit('Saved')"
      @deleted="afterEdit('Deleted')"
    />
  </div>
</template>
