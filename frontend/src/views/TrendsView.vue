<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import DailyChart from "../components/DailyChart.vue";
import GamePanel from "../components/GamePanel.vue";
import HeatGrid from "../components/HeatGrid.vue";
import { api, ApiError, timeZone, type Stats, type Tracker } from "../lib/api";
import { changeSentence, formatNumber, quantity, shortDate, timeSince } from "../lib/format";

const trackers = ref<Tracker[]>([]);
const trackerId = ref<number | null>(null);
const days = ref(30);
const stats = ref<Stats | null>(null);
const error = ref("");
const loaded = ref(false);

const RANGES = [7, 30, 90, 365];
let latestRequest = 0;

const tracker = computed(() => trackers.value.find((t) => t.id === trackerId.value));
const summary = computed(() => stats.value?.summary);
const triggerPeak = computed(() =>
  Math.max(1, ...(stats.value?.triggers ?? []).map((t) => t.uses + t.urges)),
);
const hasUses = computed(() => (summary.value?.uses_in_window ?? 0) > 0);
// The panel above already says all of this for someone who has stopped.
const stopped = computed(() => Boolean(stats.value?.game.stopped));

const weekLine = computed(() => {
  const s = summary.value;
  if (!s || !tracker.value || s.recent_7 === null) return null;
  const amount = quantity(s.recent_7, tracker.value.unit);
  const change = changeSentence(s.change_pct);
  return change ? `${amount}, ${change}` : amount;
});

async function loadStats() {
  if (trackerId.value === null) return;
  // A slower earlier reply must never show up under the tracker chosen since.
  const request = ++latestRequest;
  stats.value = null;
  try {
    const result = await api<Stats>(
      `/api/trackers/${trackerId.value}/stats?days=${days.value}&tz=${encodeURIComponent(timeZone())}`,
    );
    if (request !== latestRequest) return;
    stats.value = result;
    error.value = "";
  } catch (e) {
    if (request !== latestRequest) return;
    error.value = e instanceof ApiError ? e.message : "Trends didn't load.";
  }
}

watch([trackerId, days], loadStats);

onMounted(async () => {
  try {
    const all = await api<Tracker[]>("/api/trackers?include_archived=true");
    // Hidden trackers keep their history, so they stay reachable here, after the active ones.
    trackers.value = [...all.filter((t) => !t.archived_at), ...all.filter((t) => t.archived_at)];
    trackerId.value = trackers.value[0]?.id ?? null;
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Trends didn't load.";
  }
  loaded.value = true;
});
</script>

<template>
  <div class="page wide-page">
    <h1>Trends</h1>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="loaded && !trackers.length && !error" class="lede">
      Trends appear once you're tracking something. <RouterLink to="/">Start on the Today page.</RouterLink>
    </p>

    <template v-if="trackers.length">
      <div class="controls">
        <div v-if="trackers.length > 1" class="chips" role="group" aria-label="Choose what to show">
          <button
            v-for="t in trackers"
            :key="t.id"
            type="button"
            class="chip"
            :aria-pressed="t.id === trackerId"
            @click="trackerId = t.id"
          >
            {{ t.name }}<template v-if="t.archived_at"> (hidden)</template>
          </button>
        </div>
        <div class="chips" role="group" aria-label="Time range">
          <button
            v-for="r in RANGES"
            :key="r"
            type="button"
            class="chip"
            :aria-pressed="r === days"
            @click="days = r"
          >
            {{ r }} days
          </button>
        </div>
      </div>

      <template v-if="stats && summary && tracker">
        <GamePanel :game="stats.game" :tracker="tracker" />

        <dl class="facts">
          <div v-if="weekLine && !stopped">
            <dt>Last 7 full days</dt>
            <dd>{{ weekLine }}</dd>
          </div>
          <div v-if="!stopped">
            <dt>Time since last logged</dt>
            <dd>{{ summary.last_use_at ? timeSince(summary.last_use_at) : "Nothing logged yet" }}</dd>
          </div>
          <div v-if="!stopped && summary.within_goal && summary.within_goal.of > 0">
            <dt>Days within your goal</dt>
            <dd>{{ summary.within_goal.days }} of {{ summary.within_goal.of }}</dd>
          </div>
          <div>
            <dt>{{ stopped ? "Urges in this period" : "Urges without use" }}</dt>
            <dd>
              {{ summary.urges_in_window }}
            </dd>
          </div>
          <div v-if="summary.average_craving !== null">
            <dt>Average craving</dt>
            <dd>{{ summary.average_craving }} out of 10</dd>
          </div>
        </dl>

        <p v-if="summary.unlogged_days && !stopped" class="section-note">
          {{ summary.unlogged_days }} {{ summary.unlogged_days === 1 ? "day has" : "days have" }} no logs in this period. They show as empty and don't count toward goals, records or levels.
        </p>

        <p v-if="stopped && !hasUses" class="section-note">No use logged in this period.</p>
        <section v-else>
          <h2>Use per day</h2>
          <p class="section-note">{{ quantity(summary.amount_in_window, tracker.unit) }} since {{ shortDate(stats.window_start) }}</p>
          <p v-if="tracker.standard_drinks_from" class="section-note">Standard drinks are estimates, not safe levels. Counted this way since {{ shortDate(tracker.standard_drinks_from) }}, and earlier logs keep the amounts they were logged with.</p>
          <DailyChart :daily="stats.daily" :unit="tracker.unit" />
          <details class="table-view">
            <summary>Show as a table</summary>
            <div class="table-scroll">
              <table>
                <thead>
                  <tr><th scope="col">Date</th><th scope="col">Amount</th><th scope="col">Logs</th><th scope="col">Urges</th><th scope="col">7-day average</th></tr>
                </thead>
                <tbody>
                  <tr v-for="d in [...stats.daily].reverse()" :key="d.date">
                    <th scope="row">{{ shortDate(d.date) }}</th>
                    <td>{{ formatNumber(d.amount) }}</td>
                    <td>{{ d.uses }}</td>
                    <td>{{ d.urges }}</td>
                    <td>{{ d.average_7d === null ? "No data" : formatNumber(d.average_7d) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </details>
        </section>

        <div class="two-up">
          <section v-if="hasUses">
            <h2>When it happens</h2>
            <p class="section-note">Number of logs by day and time</p>
            <HeatGrid :heatmap="stats.heatmap" />
          </section>

          <section v-if="stats.triggers.length">
            <h2>What was going on</h2>
            <div class="legend" aria-hidden="true">
              <span><i class="swatch bar"></i>Used</span>
              <span><i class="swatch urge-swatch"></i>Urge without use</span>
            </div>
            <ul class="trigger-list">
              <li v-for="t in stats.triggers" :key="t.trigger">
                <span class="trigger-name">{{ t.trigger }}</span>
                <span class="trigger-count">{{ t.uses }} used, {{ t.urges }} {{ t.urges === 1 ? "urge" : "urges" }}</span>
                <span class="trigger-bar" aria-hidden="true">
                  <i v-if="t.uses" class="seg seg-use" :style="{ width: `${(t.uses / triggerPeak) * 100}%` }"></i>
                  <i v-if="t.urges" class="seg seg-urge" :style="{ width: `${(t.urges / triggerPeak) * 100}%` }"></i>
                </span>
              </li>
            </ul>
          </section>
        </div>
      </template>
    </template>
  </div>
</template>
