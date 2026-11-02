<script setup lang="ts">
import { computed } from "vue";
import { quantity } from "../lib/format";
import { standardDrinks } from "../lib/drinks";

export interface DrinkForm {
  name: string;
  servings: number | "";
  serving_ml: number | "";
  abv: number | "";
}

const form = defineModel<DrinkForm>({ required: true });

const alcoholFree = computed(() => form.value.abv === 0);
const preview = computed(() => {
  const { servings, serving_ml: ml, abv } = form.value;
  if (!servings || !ml || !abv) return null;
  return `${servings} × ${ml} ml at ${abv}% = ${quantity(standardDrinks(servings, ml, abv), "standard drink")}`;
});
</script>

<template>
  <label class="field">
    <span>Drink or brand</span>
    <input v-model="form.name" required maxlength="60" pattern=".*\S.*" title="Enter a name for the drink" autocomplete="off" />
  </label>
  <div class="field-row drink-numbers">
    <label class="field">
      <span>How many</span>
      <input v-model.number="form.servings" type="number" min="1" max="50" step="1" inputmode="numeric" required />
    </label>
    <label class="field">
      <span>Each (ml)</span>
      <input v-model.number="form.serving_ml" type="number" min="1" max="5000" step="any" inputmode="decimal" required />
    </label>
    <label class="field">
      <span>ABV (%)</span>
      <input v-model.number="form.abv" type="number" min="0" max="100" step="any" inputmode="decimal" required />
    </label>
  </div>
  <p v-if="alcoholFree" class="section-note" role="status">Alcohol-free drinks don't need logging here.</p>
  <p v-else class="drink-preview" role="status">
    <template v-if="preview">{{ preview }}<small>An estimate, not a safe level.</small></template>
  </p>
</template>
