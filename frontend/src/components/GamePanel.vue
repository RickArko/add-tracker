<script setup lang="ts">
import { computed } from "vue";
import type { Game, Tracker } from "../lib/api";
import { duration, formatNumber, quantity, shortDate } from "../lib/format";
import TallyMarks from "./TallyMarks.vue";

const props = defineProps<{ game: Game; tracker: Tracker }>();

const level = computed(() => props.game.level);
const records = computed(() => props.game.records);
const unit = computed(() => props.tracker.unit);

const LABELS: Record<string, { name: string; value: (n: number) => string }> = {
  gap: { name: "Longest stretch without use", value: (n) => duration(n) },
  urges: { name: "Urges without use", value: (n) => formatNumber(n) },
  within: { name: "Days within your goal", value: (n) => formatNumber(n) },
  logged: { name: "Days you logged", value: (n) => formatNumber(n) },
};

const milestones = computed(() =>
  props.game.milestones.map((m) => ({
    ...m,
    name: LABELS[m.key].name,
    now: LABELS[m.key].value(m.value),
    target: m.next === null ? null : LABELS[m.key].value(m.next),
    share: m.next === null ? 100 : Math.min(100, (m.value / m.next) * 100),
  })),
);
const trend = computed(() => {
  const t = props.game.trend;
  if (!t) return null;
  if (t.per_week === 0) return `Flat over the last ${t.days_used} days`;
  const direction = t.per_week < 0 ? "Falling" : "Rising";
  return `${direction} ${quantity(Math.abs(t.per_week), unit.value)} a day, each week`;
});
</script>

<template>
  <section v-if="level" class="level-panel">
    <h2>Level {{ level.level }} of {{ level.total_levels }}</h2>
    <template v-if="level.at_zero">
      <p class="level-limit">You're at zero.</p>
      <p class="level-progress">
        <TallyMarks v-if="level.days_cleared" :count="level.days_cleared" />
        <span>{{ level.days_cleared }} {{ level.days_cleared === 1 ? "day" : "days" }} without use at this level</span>
      </p>
    </template>
    <template v-else>
      <p class="level-limit">Limit {{ quantity(level.limit, unit) }} a day</p>
      <p class="level-progress">
        <TallyMarks v-if="level.days_cleared" :count="Math.min(level.days_cleared, level.clear_days)" />
        <span>{{ Math.min(level.days_cleared, level.clear_days) }} of {{ level.clear_days }} days cleared. Days add up, so a hard day doesn't reset them.</span>
      </p>
    </template>
    <dl class="facts">
      <div>
        <dt>Not used, compared with your {{ quantity(level.baseline, unit) }} start</dt>
        <dd>{{ quantity(level.banked, unit) }}</dd>
      </div>
      <div v-if="level.zero_by">
        <dt>Earliest you could reach zero at this pace</dt>
        <dd>{{ shortDate(level.zero_by) }}</dd>
      </div>
      <div v-if="trend">
        <dt>Trend over the last {{ game.trend?.days_used }} full days</dt>
        <dd>{{ trend }}</dd>
      </div>
      <div v-if="game.trend?.zero_by">
        <dt>Where that trend reaches zero</dt>
        <dd>{{ shortDate(game.trend.zero_by) }}</dd>
      </div>
    </dl>
  </section>

  <section>
    <h2>Your records</h2>
    <dl class="facts">
      <div v-if="records.lowest_day">
        <dt>Lowest day</dt>
        <dd>{{ quantity(records.lowest_day.amount, unit) }} on {{ shortDate(records.lowest_day.date) }}</dd>
      </div>
      <div v-if="records.lowest_week">
        <dt>Lowest 7 days in a row</dt>
        <dd>{{ quantity(records.lowest_week.amount, unit) }}, ending {{ shortDate(records.lowest_week.ending) }}</dd>
      </div>
      <div>
        <dt>Longest stretch without use</dt>
        <dd>{{ duration(records.longest_gap_hours) }}</dd>
      </div>
      <div v-if="game.typical_gap_hours !== null">
        <dt>Typical time between uses this week</dt>
        <dd>{{ duration(game.typical_gap_hours) }}</dd>
      </div>
    </dl>
  </section>

  <section>
    <h2>Milestones</h2>
    <ul class="milestones">
      <li v-for="m in milestones" :key="m.key">
        <span class="milestone-name">{{ m.name }}</span>
        <span class="milestone-count">
          <template v-if="m.target">{{ m.now }} of {{ m.target }}</template>
          <template v-else>{{ m.now }}, all reached</template>
        </span>
        <span class="milestone-bar" aria-hidden="true"><i :style="{ width: `${m.share}%` }"></i></span>
      </li>
    </ul>
  </section>
</template>
