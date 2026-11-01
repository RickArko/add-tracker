<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import type { DayStat } from "../lib/api";
import { formatNumber, niceMax, quantity, shortDate } from "../lib/format";

const props = defineProps<{ daily: DayStat[]; unit: string }>();

const host = ref<HTMLElement>();
const width = ref(640);
const HEIGHT = 240;
const M = { top: 12, right: 8, bottom: 26, left: 34 };
const active = ref<number | null>(null);

let observer: ResizeObserver | undefined;
onMounted(() => {
  observer = new ResizeObserver(([e]) => (width.value = Math.max(260, e.contentRect.width)));
  if (host.value) observer.observe(host.value);
});
onBeforeUnmount(() => observer?.disconnect());

const plotW = computed(() => width.value - M.left - M.right);
const plotH = HEIGHT - M.top - M.bottom;
const yMax = computed(() =>
  niceMax(Math.max(1, ...props.daily.flatMap((d) => [d.amount, d.average_7d ?? 0, d.limit ?? 0]))),
);
const y = (value: number) => M.top + plotH - (value / yMax.value) * plotH;
const slot = computed(() => plotW.value / Math.max(1, props.daily.length));
const barW = computed(() => Math.max(2, Math.min(slot.value - (slot.value > 6 ? 2 : 1), 32)));
const cx = (i: number) => M.left + slot.value * i + slot.value / 2;

const ticks = computed(() => [0, 0.5, 1].map((f) => f * yMax.value));

function barPath(i: number, amount: number) {
  const x = cx(i) - barW.value / 2;
  const top = y(amount);
  const base = y(0);
  const r = Math.min(4, barW.value / 2, base - top);
  return `M${x} ${base} V${top + r} Q${x} ${top} ${x + r} ${top} H${x + barW.value - r} Q${x + barW.value} ${top} ${x + barW.value} ${top + r} V${base} Z`;
}

const bars = computed(() =>
  props.daily.flatMap((d, i) => (d.amount > 0 ? [{ i, d: barPath(i, d.amount) }] : [])),
);
const averageLine = computed(() => {
  let path = "";
  let drawing = false;
  props.daily.forEach((d, i) => {
    if (d.average_7d === null) {
      drawing = false;
      return;
    }
    path += `${drawing ? "L" : "M"}${cx(i)} ${y(d.average_7d)} `;
    drawing = true;
  });
  return path;
});
// A stepped line, because each past day keeps the limit it had at the time.
const limitLine = computed(() => {
  let path = "";
  let previous: number | null = null;
  props.daily.forEach((d, i) => {
    const left = M.left + slot.value * i;
    if (d.limit === null) {
      previous = null;
      return;
    }
    path += `${previous === null ? "M" : "L"}${left} ${y(d.limit)} L${left + slot.value} ${y(d.limit)} `;
    previous = d.limit;
  });
  return path;
});
const xLabels = computed(() => {
  const n = props.daily.length;
  const picks = n <= 1 ? [0] : n <= 7 ? [0, n - 1] : [0, Math.floor((n - 1) / 2), n - 1];
  return picks.map((i) => ({ i, text: shortDate(props.daily[i].date) }));
});

function onPointer(event: PointerEvent) {
  const box = (event.currentTarget as SVGElement).getBoundingClientRect();
  const i = Math.floor((event.clientX - box.left - M.left) / slot.value);
  active.value = i >= 0 && i < props.daily.length ? i : null;
}
function onKey(event: KeyboardEvent) {
  const last = props.daily.length - 1;
  if (event.key === "ArrowLeft") active.value = Math.max(0, (active.value ?? last + 1) - 1);
  else if (event.key === "ArrowRight") active.value = Math.min(last, (active.value ?? -1) + 1);
  else return;
  event.preventDefault();
}

const tip = computed(() => {
  if (active.value === null) return null;
  const d = props.daily[active.value];
  if (!d) return null;
  const onRight = cx(active.value) > width.value / 2;
  return {
    d,
    style: onRight
      ? { right: `${width.value - cx(active.value) + 10}px` }
      : { left: `${cx(active.value) + 10}px` },
  };
});
const summary = computed(() => {
  const total = props.daily.reduce((sum, d) => sum + d.amount, 0);
  return `Bar chart of daily use over ${props.daily.length} days, ${quantity(total, props.unit)} in total. Use left and right arrow keys to read each day.`;
});
</script>

<template>
  <div class="legend" aria-hidden="true">
    <span><i class="swatch bar"></i>Each day</span>
    <span><i class="swatch line"></i>7-day average</span>
    <span v-if="limitLine"><i class="swatch limit"></i>Your limit</span>
  </div>
  <div ref="host" class="chart">
    <svg
      :width="width"
      :height="HEIGHT"
      role="img"
      :aria-label="summary"
      tabindex="0"
      @pointermove="onPointer"
      @pointerdown="onPointer"
      @pointerleave="active = null"
      @blur="active = null"
      @keydown="onKey"
    >
      <g class="grid">
        <template v-for="t in ticks" :key="t">
          <line :x1="M.left" :x2="width - M.right" :y1="y(t)" :y2="y(t)" />
          <text :x="M.left - 8" :y="y(t) + 4" text-anchor="end">{{ formatNumber(t) }}</text>
        </template>
      </g>
      <rect v-if="active !== null" class="band" :x="cx(active) - slot / 2" :y="M.top" :width="slot" :height="plotH" />
      <path v-for="bar in bars" :key="bar.i" :d="bar.d" class="bar" />
      <path v-if="limitLine" class="limit" :d="limitLine" />
      <path :d="averageLine" class="average" />
      <g class="x-axis">
        <text
          v-for="(label, n) in xLabels"
          :key="label.i"
          :x="n === 0 ? M.left : n === xLabels.length - 1 ? width - M.right : cx(label.i)"
          :y="HEIGHT - 6"
          :text-anchor="n === 0 ? 'start' : n === xLabels.length - 1 ? 'end' : 'middle'"
        >
          {{ label.text }}
        </text>
      </g>
    </svg>
    <div v-if="tip" class="tip" :style="tip.style" role="status">
      <strong>{{ shortDate(tip.d.date) }}</strong>
      <span>{{ quantity(tip.d.amount, unit) }}</span>
      <span v-if="tip.d.average_7d !== null">7-day average {{ formatNumber(tip.d.average_7d) }}</span>
      <span v-if="tip.d.limit !== null">Limit that day {{ formatNumber(tip.d.limit) }}</span>
      <span v-if="tip.d.urges">{{ tip.d.urges }} {{ tip.d.urges === 1 ? "urge" : "urges" }} without use</span>
    </div>
  </div>
</template>
