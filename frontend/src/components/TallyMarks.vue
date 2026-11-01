<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { tallyGroups } from "../lib/format";

const props = withDefaults(defineProps<{ count: number; max?: number }>(), { max: 40 });

const STROKE_GAP = 11;
const GROUP_GAP = 15;
const HEIGHT = 44;

// A small fixed wobble per position, so marks look handwritten but never shift between renders.
const wobble = (i: number, salt: number) => ((Math.sin(i * 12.9898 + salt * 78.233) * 43758.5453) % 1) * 2.2;

const shown = computed(() => Math.min(props.count, props.max));
const hidden = computed(() => props.count - shown.value);

const groups = computed(() => {
  let x = 4;
  let index = 0;
  return tallyGroups(shown.value).map((size) => {
    const uprights = Math.min(size, 4);
    const strokes = [];
    const startX = x;
    for (let u = 0; u < uprights; u++) {
      strokes.push({
        index: index++,
        d: `M${x + wobble(index, 1)} ${5 + wobble(index, 2)} L${x + wobble(index, 3)} ${HEIGHT - 5 + wobble(index, 4)}`,
      });
      x += STROKE_GAP;
    }
    if (size === 5) {
      strokes.push({
        index: index++,
        d: `M${startX - 5} ${HEIGHT - 11 + wobble(index, 2)} L${x - STROKE_GAP + 5} ${11 + wobble(index, 3)}`,
      });
    }
    const width = x - STROKE_GAP + 8 - startX + 4;
    x += GROUP_GAP - STROKE_GAP + 8;
    return { strokes, startX, width };
  });
});

const totalWidth = (group: { startX: number; width: number }) => group.startX + group.width;

// Only a mark just added animates; marks already on the page stay put.
const animateFrom = ref(props.count);
watch(
  () => props.count,
  (next, prev) => {
    animateFrom.value = next > prev ? prev : next;
  },
);
</script>

<template>
  <span class="tally" role="img" :aria-label="`${count} logged`">
    <svg
      v-for="(group, g) in groups"
      :key="g"
      :viewBox="`${group.startX - 7} 0 ${group.width + 6} ${HEIGHT}`"
      :width="group.width + 6"
      :height="HEIGHT"
      aria-hidden="true"
      :data-end="totalWidth(group)"
    >
      <path
        v-for="stroke in group.strokes"
        :key="stroke.index"
        :d="stroke.d"
        pathLength="1"
        :class="{ fresh: stroke.index >= animateFrom }"
      />
    </svg>
    <span v-if="hidden > 0" class="tally-more">+{{ hidden }} more</span>
  </span>
</template>
