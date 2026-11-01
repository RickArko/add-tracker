<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{ heatmap: number[][] }>();

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const BLOCKS = ["12am", "4am", "8am", "12pm", "4pm", "8pm"];
const ENDS = ["4am", "8am", "12pm", "4pm", "8pm", "12am"];

const rows = computed(() =>
  props.heatmap.map((hours) =>
    BLOCKS.map((_, b) => hours.slice(b * 4, b * 4 + 4).reduce((sum, n) => sum + n, 0)),
  ),
);
const peak = computed(() => Math.max(1, ...rows.value.flat()));

function cellStyle(count: number) {
  if (!count) return {};
  const share = 18 + (count / peak.value) * 82;
  return {
    backgroundColor: `color-mix(in oklab, var(--use) ${share}%, var(--surface))`,
    color: share > 58 ? "var(--on-use)" : "var(--ink)",
  };
}
</script>

<template>
  <table class="heat">
    <thead>
      <tr>
        <td></td>
        <th v-for="block in BLOCKS" :key="block" scope="col">{{ block }}</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="(row, d) in rows" :key="DAYS[d]">
        <th scope="row">{{ DAYS[d] }}</th>
        <td
          v-for="(count, b) in row"
          :key="b"
          :style="cellStyle(count)"
          :title="`${DAYS[d]} ${BLOCKS[b]} to ${ENDS[b]}: ${count}`"
        >
          {{ count || "" }}
        </td>
      </tr>
    </tbody>
  </table>
</template>
