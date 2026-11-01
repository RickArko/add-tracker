<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { api, ApiError, timeZone, type Stats, type Tracker } from "../lib/api";
import { formatNumber, quantity, shortDate } from "../lib/format";

const props = defineProps<{ tracker: Tracker }>();
const emit = defineEmits<{ saved: []; cancel: [] }>();

const baseline = ref<number | "">(props.tracker.baseline_amount ?? props.tracker.daily_limit ?? "");
const step = ref<number | "">(props.tracker.step_amount ?? props.tracker.default_amount);
const clearDays = ref<number | "">(props.tracker.clear_days ?? 7);
const recent = ref<number | null>(null);
const error = ref("");
const busy = ref(false);

const preview = computed(() => {
  const b = Number(baseline.value);
  const s = Number(step.value);
  const c = Number(clearDays.value);
  if (!(b > 0 && s > 0 && c > 0) || s > b) return null;
  const steps = Math.ceil(Math.round((b / s) * 1e6) / 1e6);
  const days = steps * c;
  const date = new Date();
  date.setDate(date.getDate() + days);
  return {
    levels: steps + 1,
    days,
    date: shortDate(date.toLocaleDateString("en-CA")),
    year: date.getFullYear(),
  };
});

onMounted(async () => {
  try {
    const stats = await api<Stats>(
      `/api/trackers/${props.tracker.id}/stats?days=7&tz=${encodeURIComponent(timeZone())}`,
    );
    if (stats.summary.recent_7 !== null) recent.value = stats.summary.recent_7 / 7;
  } catch {
    // The hint is optional, so setup carries on without it.
  }
});

async function submit() {
  busy.value = true;
  error.value = "";
  try {
    await api(`/api/trackers/${props.tracker.id}/plan?tz=${encodeURIComponent(timeZone())}`, "PUT", {
      baseline_amount: baseline.value,
      step_amount: step.value,
      clear_days: clearDays.value,
    });
    emit("saved");
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "That didn't save. Try again.";
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <form class="tracker-form" @submit.prevent="submit">
    <h3>Levels for {{ tracker.name }}</h3>
    <p>Each level lowers your daily limit by one step. You move down only when you choose to, after enough days within the limit. A day counts once it has a log or you confirm no use, so skipping logs earns nothing.</p>
    <div class="field-row">
      <label class="field grow">
        <span>Starting amount a day ({{ tracker.unit }})</span>
        <input v-model.number="baseline" type="number" min="0.01" step="any" inputmode="decimal" required />
        <small v-if="recent !== null">You averaged {{ formatNumber(recent) }} a day over the last 7 full days.</small>
      </label>
      <label class="field amount">
        <span>Each step down ({{ tracker.unit }})</span>
        <input v-model.number="step" type="number" min="0.01" step="any" inputmode="decimal" required />
      </label>
      <label class="field amount">
        <span>Days to clear a level</span>
        <input v-model.number="clearDays" type="number" min="1" max="90" step="1" inputmode="numeric" required />
      </label>
    </div>
    <p v-if="preview" class="plan-preview">
      {{ preview.levels }} levels. Zero by {{ preview.date }}, {{ preview.year }} at the earliest ({{ preview.days }} days). Going slower is fine.
    </p>
    <p class="section-note">If this is a prescribed medication, or stopping has made you unwell before, ask a clinician about your pace first.</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div class="actions">
      <button class="primary" type="submit" :disabled="busy">Save levels</button>
      <button type="button" class="quiet" @click="emit('cancel')">Cancel</button>
    </div>
    <p class="section-note">Your limit starts at {{ baseline ? quantity(Number(baseline), tracker.unit) : "your starting amount" }} unless it's already lower.</p>
  </form>
</template>
