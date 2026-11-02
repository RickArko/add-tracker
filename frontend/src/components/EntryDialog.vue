<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { api, ApiError, type Entry, type Tracker } from "../lib/api";
import { TRIGGERS } from "../lib/catalog";
import DrinkFields, { type DrinkForm } from "./DrinkFields.vue";
import { toLocalInput } from "../lib/format";

const props = defineProps<{ entry: Entry; tracker: Tracker | undefined }>();
const emit = defineEmits<{ close: []; saved: [Entry]; deleted: [Entry] }>();

const dialog = ref<HTMLDialogElement>();
const original = toLocalInput(new Date(props.entry.occurred_at));
const occurredAt = ref(original);
const amount = ref<number | "">(props.entry.amount ?? "");
const drink = ref<DrinkForm | null>(
  props.entry.drink_name
    ? {
        name: props.entry.drink_name,
        servings: props.entry.servings ?? 1,
        serving_ml: props.entry.serving_ml ?? "",
        abv: props.entry.abv ?? "",
      }
    : null,
);
const craving = ref<number | null>(props.entry.craving);
const trigger = ref(props.entry.trigger ?? "");
const note = ref(props.entry.note ?? "");
const error = ref("");
const busy = ref(false);
const confirmingDelete = ref(false);
const nowMax = toLocalInput(new Date());

const options = computed(() =>
  trigger.value && !TRIGGERS.includes(trigger.value) ? [...TRIGGERS, trigger.value] : TRIGGERS,
);
const heading = computed(() => {
  const kind = props.entry.kind === "use" ? "Use" : "Urge";
  return props.tracker ? `${kind} of ${props.tracker.name}`.replace("Urge of", "Urge for") : kind;
});

onMounted(() => dialog.value?.showModal());

async function run(action: () => Promise<void>) {
  busy.value = true;
  error.value = "";
  try {
    await action();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "That didn't save. Try again.";
  } finally {
    busy.value = false;
  }
}

const save = () =>
  run(async () => {
    const body: Record<string, unknown> = {
      craving: craving.value,
      trigger: trigger.value,
      note: note.value,
    };
    if (drink.value) {
      if (!drink.value.abv) throw new ApiError(422, "Alcohol-free drinks don't need logging here.");
      body.drink = drink.value;
    } else if (props.entry.kind === "use") {
      body.amount = amount.value === "" ? null : amount.value;
    }
    if (occurredAt.value !== original) body.occurred_at = new Date(occurredAt.value).toISOString();
    emit("saved", await api<Entry>(`/api/entries/${props.entry.id}`, "PATCH", body));
  });

const remove = () =>
  run(async () => {
    await api(`/api/entries/${props.entry.id}`, "DELETE");
    emit("deleted", props.entry);
  });
</script>

<template>
  <dialog ref="dialog" class="sheet" aria-labelledby="entry-heading" @close="emit('close')">
    <form @submit.prevent="save">
      <h2 id="entry-heading">{{ heading }}</h2>

      <div class="field-row">
        <label class="field grow">
          <span>When</span>
          <input v-model="occurredAt" type="datetime-local" :max="nowMax" required />
        </label>
        <label v-if="entry.kind === 'use' && !drink" class="field amount">
          <span>Amount<template v-if="tracker"> ({{ tracker.unit }})</template></span>
          <input v-model.number="amount" type="number" min="0.01" step="any" inputmode="decimal" required />
        </label>
      </div>

      <DrinkFields v-if="drink" v-model="drink" />

      <fieldset class="field">
        <legend>How strong was the craving? <small>0 is none, 10 is the strongest</small></legend>
        <div class="scale">
          <button
            v-for="n in 11"
            :key="n"
            type="button"
            :aria-pressed="craving === n - 1"
            @click="craving = craving === n - 1 ? null : n - 1"
          >
            {{ n - 1 }}
          </button>
        </div>
      </fieldset>

      <fieldset class="field">
        <legend>What was going on?</legend>
        <div class="chips">
          <button
            v-for="option in options"
            :key="option"
            type="button"
            class="chip"
            :aria-pressed="trigger === option"
            @click="trigger = trigger === option ? '' : option"
          >
            {{ option }}
          </button>
        </div>
      </fieldset>

      <label class="field">
        <span>Note</span>
        <textarea v-model="note" rows="2" maxlength="1000"></textarea>
      </label>

      <p v-if="error" class="error" role="alert">{{ error }}</p>

      <div class="actions">
        <button class="primary" type="submit" :disabled="busy">Save</button>
        <button type="button" class="quiet" @click="dialog?.close()">Cancel</button>
        <button v-if="!confirmingDelete" type="button" class="quiet push-right" @click="confirmingDelete = true">Delete entry</button>
        <button v-else type="button" class="danger push-right" :disabled="busy" @click="remove">Confirm delete</button>
      </div>
    </form>
  </dialog>
</template>
