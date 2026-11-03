<script setup lang="ts">
import { onMounted, ref } from "vue";
import type { Drink } from "../lib/api";
import { DRINK_TYPES, type DrinkType } from "../lib/drinks";
import DrinkFields, { type DrinkForm } from "./DrinkFields.vue";

const emit = defineEmits<{ close: []; chosen: [Drink] }>();

const dialog = ref<HTMLDialogElement>();
const type = ref<DrinkType | null>(null);
const form = ref<DrinkForm>({ name: "", servings: 1, serving_ml: "", abv: "" });

function chooseType(next: DrinkType) {
  type.value = next;
  form.value = { name: next.name, servings: form.value.servings, serving_ml: next.sizes[0]!.ml, abv: next.abv };
}

function submit() {
  const { name, servings, serving_ml, abv } = form.value;
  if (!servings || !serving_ml || !abv) return;
  emit("chosen", { name: name.trim(), servings, serving_ml, abv });
  dialog.value?.close();
}

onMounted(() => dialog.value?.showModal());
</script>

<template>
  <dialog ref="dialog" class="sheet" aria-labelledby="drink-heading" @close="emit('close')">
    <form @submit.prevent="submit">
      <h2 id="drink-heading">Choose a drink</h2>
      <fieldset class="field">
        <legend>What kind?</legend>
        <div class="chips">
          <button
            v-for="option in DRINK_TYPES"
            :key="option.name"
            type="button"
            class="chip"
            :aria-pressed="type?.name === option.name"
            @click="chooseType(option)"
          >
            {{ option.name }}
          </button>
        </div>
      </fieldset>
      <template v-if="type">
        <fieldset class="field">
          <legend>What size?</legend>
          <div class="chips">
            <button
              v-for="size in type.sizes"
              :key="size.ml"
              type="button"
              class="chip"
              :aria-pressed="form.serving_ml === size.ml"
              @click="form.serving_ml = size.ml"
            >
              {{ size.label }}
            </button>
          </div>
        </fieldset>
        <DrinkFields v-model="form" />
      </template>
      <div class="actions">
        <button class="primary" type="submit" :disabled="!type || !form.abv">Log it</button>
        <button type="button" class="quiet" @click="dialog?.close()">Cancel</button>
      </div>
    </form>
  </dialog>
</template>
