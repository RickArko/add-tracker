<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import EntryDialog from "../components/EntryDialog.vue";
import TallyMarks from "../components/TallyMarks.vue";
import TrackerForm from "../components/TrackerForm.vue";
import { api, ApiError, timeZone, type Entry, type TodayTracker, type Tracker } from "../lib/api";
import { formatNumber, longDate, quantity, timeSince, unitLabel } from "../lib/format";

const trackers = ref<TodayTracker[]>([]);
const loaded = ref(false);
const loadError = ref("");
const editing = ref<Entry | null>(null);
const toast = ref<{ text: string; entry?: Entry } | null>(null);
const today = ref(new Date());
let toastTimer: number | undefined;

const editingTracker = computed(() =>
  trackers.value.find((t) => t.id === editing.value?.tracker_id),
);

async function load() {
  today.value = new Date();
  try {
    trackers.value = await api<TodayTracker[]>(`/api/today?tz=${encodeURIComponent(timeZone())}`);
    loadError.value = "";
  } catch (e) {
    loadError.value = e instanceof ApiError ? e.message : "Today's log didn't load.";
  }
  loaded.value = true;
}

function showToast(text: string, entry?: Entry) {
  toast.value = { text, entry };
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => (toast.value = null), 8000);
}

async function log(tracker: TodayTracker, kind: "use" | "urge") {
  // Update first, so a tap feels instant even on a slow connection.
  if (kind === "use") {
    tracker.uses_today += 1;
    tracker.amount_today += tracker.default_amount;
  } else {
    tracker.urges_today += 1;
  }
  try {
    const entry = await api<Entry>("/api/entries", "POST", { tracker_id: tracker.id, kind });
    showToast(
      kind === "use" ? `Logged ${quantity(entry.amount ?? 0, tracker.unit)}` : "Logged urge",
      entry,
    );
    if (kind === "use") tracker.last_use_at = entry.occurred_at;
  } catch (e) {
    if (kind === "use") {
      tracker.uses_today -= 1;
      tracker.amount_today -= tracker.default_amount;
    } else {
      tracker.urges_today -= 1;
    }
    showToast(e instanceof ApiError ? e.message : "That didn't save. Try again.");
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

function limitNote(t: TodayTracker): string {
  if (t.daily_limit === null) return `${quantity(t.amount_today, t.unit)} today`;
  return `${formatNumber(t.amount_today)} of ${quantity(t.daily_limit, t.unit)} today`;
}

const onVisible = () => {
  if (document.visibilityState === "visible") void load();
};
onMounted(() => {
  void load();
  document.addEventListener("visibilitychange", onVisible);
});
onBeforeUnmount(() => {
  document.removeEventListener("visibilitychange", onVisible);
  window.clearTimeout(toastTimer);
});
</script>

<template>
  <div class="page">
    <h1 class="date">{{ longDate(today) }}</h1>

    <p v-if="loadError" class="error" role="alert">
      {{ loadError }} <button class="link" type="button" @click="load">Try again</button>
    </p>

    <section v-if="loaded && !trackers.length && !loadError" class="first-run">
      <p class="lede">Log each time with one tap, and a pattern starts to show within days. Everything stays in your account.</p>
      <TrackerForm @saved="created" />
    </section>

    <ul class="today-list">
      <li v-for="t in trackers" :key="t.id" class="today-row" :data-tracker="t.name">
        <h2>{{ t.name }}</h2>
        <p class="tally-line">
          <TallyMarks v-if="t.uses_today" :count="t.uses_today" />
          <span v-else class="none-yet">No logs yet today</span>
        </p>
        <p class="today-facts">
          <span class="today-total">{{ limitNote(t) }}</span>
          <span v-if="t.urges_today">{{ t.urges_today }} {{ t.urges_today === 1 ? "urge" : "urges" }} without use</span>
          <span v-if="t.last_use_at">Last logged {{ timeSince(t.last_use_at) }} ago</span>
        </p>
        <div class="log-actions">
          <button class="log-use" type="button" @click="log(t, 'use')">
            Log {{ formatNumber(t.default_amount) }} {{ unitLabel(t.unit, t.default_amount) }}
          </button>
          <button class="log-urge" type="button" @click="log(t, 'urge')">Had an urge, didn't use</button>
        </div>
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
