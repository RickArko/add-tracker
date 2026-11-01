<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import EntryDialog from "../components/EntryDialog.vue";
import { api, ApiError, type Entry, type Tracker } from "../lib/api";
import { clockTime, longDate, quantity } from "../lib/format";

const PAGE = 50;
const trackers = ref<Tracker[]>([]);
const filter = ref<number | null>(null);
const entries = ref<Entry[]>([]);
const more = ref(false);
const loaded = ref(false);
const error = ref("");
const editing = ref<Entry | null>(null);

const trackerFor = (id: number) => trackers.value.find((t) => t.id === id);

const days = computed(() => {
  const groups: { label: string; entries: Entry[] }[] = [];
  for (const entry of entries.value) {
    const label = longDate(new Date(entry.occurred_at));
    if (groups.at(-1)?.label !== label) groups.push({ label, entries: [] });
    groups.at(-1)!.entries.push(entry);
  }
  return groups;
});

function describe(entry: Entry): string {
  const tracker = trackerFor(entry.tracker_id);
  if (entry.kind === "urge") return "Urge without use";
  return tracker ? quantity(entry.amount ?? 0, tracker.unit) : String(entry.amount);
}

async function fetchPage(offset: number) {
  const query = new URLSearchParams({ limit: String(PAGE + 1), offset: String(offset) });
  if (filter.value !== null) query.set("tracker_id", String(filter.value));
  try {
    const page = await api<Entry[]>(`/api/entries?${query}`);
    more.value = page.length > PAGE;
    const rows = page.slice(0, PAGE);
    entries.value = offset ? [...entries.value, ...rows] : rows;
    error.value = "";
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "History didn't load.";
  }
}

async function reloadAll() {
  // Re-read everything on screen, so editing an old entry doesn't jump the list back to page one.
  const count = Math.max(PAGE, entries.value.length);
  const query = new URLSearchParams({ limit: String(Math.min(200, count + 1)), offset: "0" });
  if (filter.value !== null) query.set("tracker_id", String(filter.value));
  try {
    const page = await api<Entry[]>(`/api/entries?${query}`);
    const size = Math.min(200, count + 1) - 1;
    more.value = page.length > size;
    entries.value = page.slice(0, size);
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "History didn't load.";
  }
}

async function afterEdit() {
  editing.value = null;
  await reloadAll();
}

watch(filter, () => fetchPage(0));

onMounted(async () => {
  try {
    trackers.value = await api<Tracker[]>("/api/trackers?include_archived=true");
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "History didn't load.";
  }
  await fetchPage(0);
  loaded.value = true;
});
</script>

<template>
  <div class="page">
    <h1>History</h1>
    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <div v-if="trackers.length > 1" class="chips controls" role="group" aria-label="Filter history">
      <button type="button" class="chip" :aria-pressed="filter === null" @click="filter = null">All</button>
      <button
        v-for="t in trackers"
        :key="t.id"
        type="button"
        class="chip"
        :aria-pressed="filter === t.id"
        @click="filter = t.id"
      >
        {{ t.name }}
      </button>
    </div>

    <p v-if="loaded && !entries.length && !error" class="lede">
      Nothing logged yet. <RouterLink to="/">Log from the Today page.</RouterLink>
    </p>

    <section v-for="day in days" :key="day.label" class="history-day">
      <h2>{{ day.label }}</h2>
      <ul>
        <li v-for="entry in day.entries" :key="entry.id">
          <button type="button" class="history-row" @click="editing = entry">
            <span class="history-time">{{ clockTime(entry.occurred_at) }}</span>
            <span class="history-main">
              <strong>{{ trackerFor(entry.tracker_id)?.name }}</strong>
              {{ describe(entry) }}
              <small v-if="entry.trigger || entry.craving !== null">
                <template v-if="entry.trigger">{{ entry.trigger }}</template>
                <template v-if="entry.trigger && entry.craving !== null">, </template>
                <template v-if="entry.craving !== null">craving {{ entry.craving }}/10</template>
              </small>
              <small v-if="entry.note" class="history-note">{{ entry.note }}</small>
            </span>
          </button>
        </li>
      </ul>
    </section>

    <button v-if="more" type="button" class="secondary" @click="fetchPage(entries.length)">Show older entries</button>

    <EntryDialog
      v-if="editing"
      :entry="editing"
      :tracker="trackerFor(editing.tracker_id)"
      @close="editing = null"
      @saved="afterEdit"
      @deleted="afterEdit"
    />
  </div>
</template>
