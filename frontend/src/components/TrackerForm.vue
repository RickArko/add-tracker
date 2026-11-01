<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { api, ApiError, type Tracker } from "../lib/api";
import { GOALS, PRESETS, safetyNote, type Preset } from "../lib/catalog";

const props = defineProps<{ tracker?: Tracker }>();
const emit = defineEmits<{ saved: [Tracker]; cancel: [] }>();

const form = reactive({
  name: props.tracker?.name ?? "",
  category: props.tracker?.category ?? "other",
  goal: props.tracker?.goal ?? "reduce",
  unit: props.tracker?.unit ?? "time",
  default_amount: props.tracker?.default_amount ?? (1 as number | ""),
  daily_limit: props.tracker?.daily_limit ?? ("" as number | ""),
});
const chosen = ref<string | null>(props.tracker ? "edit" : null);
const error = ref("");
const busy = ref(false);

const showLimit = computed(() => form.goal !== "quit");
const safety = computed(() => safetyNote(form.category, form.goal));

function choose(preset: Preset) {
  chosen.value = preset.label;
  form.name = preset.name;
  form.category = preset.category;
  form.unit = preset.unit;
}

async function submit() {
  busy.value = true;
  error.value = "";
  const body = {
    ...form,
    default_amount: form.default_amount === "" ? 1 : form.default_amount,
    daily_limit: !showLimit.value || form.daily_limit === "" ? null : form.daily_limit,
  };
  try {
    const saved = props.tracker
      ? await api<Tracker>(`/api/trackers/${props.tracker.id}`, "PATCH", body)
      : await api<Tracker>("/api/trackers", "POST", body);
    emit("saved", saved);
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "That didn't save. Try again.";
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <form class="tracker-form" @submit.prevent="submit">
    <fieldset v-if="!tracker" class="field">
      <legend>What do you want to keep track of?</legend>
      <div class="chips">
        <button
          v-for="preset in PRESETS"
          :key="preset.label"
          type="button"
          class="chip"
          :aria-pressed="chosen === preset.label"
          @click="choose(preset)"
        >
          {{ preset.label }}
        </button>
      </div>
    </fieldset>

    <template v-if="chosen">
      <label class="field">
        <span>Name</span>
        <input v-model="form.name" required maxlength="60" autocomplete="off" />
      </label>

      <div class="field-row">
        <label class="field grow">
          <span>Count it in</span>
          <input v-model="form.unit" required maxlength="20" autocomplete="off" />
        </label>
        <label class="field amount">
          <span>Each log counts as</span>
          <input v-model.number="form.default_amount" type="number" min="0.01" step="any" inputmode="decimal" required />
        </label>
      </div>

      <fieldset class="field">
        <legend>What's your goal?</legend>
        <div class="goal-options">
          <label v-for="goal in GOALS" :key="goal.value" class="goal-option">
            <input v-model="form.goal" type="radio" name="goal" :value="goal.value" />
            <span><strong>{{ goal.label }}</strong> <small>{{ goal.hint }}</small></span>
          </label>
        </div>
      </fieldset>

      <label v-if="showLimit" class="field">
        <span>Daily limit <small>Optional, and yours to set</small></span>
        <input v-model.number="form.daily_limit" type="number" min="0" step="any" inputmode="decimal" />
      </label>

      <p v-if="safety" class="safety" role="note">
        <strong>Before you change this:</strong> {{ safety }}
        <RouterLink to="/help">Find support</RouterLink>
      </p>

      <p v-if="error" class="error" role="alert">{{ error }}</p>

      <div class="actions">
        <button class="primary" type="submit" :disabled="busy">{{ tracker ? "Save changes" : "Start tracking" }}</button>
        <button v-if="tracker" type="button" class="quiet" @click="emit('cancel')">Cancel</button>
      </div>
    </template>
  </form>
</template>
