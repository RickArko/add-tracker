<script setup lang="ts">
import { ref } from "vue";

const props = defineProps<{ code: string; buttonLabel: string }>();
const emit = defineEmits<{ done: [] }>();
const copied = ref(false);

async function copy() {
  await navigator.clipboard.writeText(props.code);
  copied.value = true;
}
</script>

<template>
  <section class="recovery-notice">
    <h2>Save your recovery code</h2>
    <p>If you forget your passphrase, this code is how you get back in. It's only shown now, and each code works once.</p>
    <p class="recovery-code" data-testid="recovery-code">{{ code }}</p>
    <div class="actions">
      <button type="button" class="secondary" @click="copy">{{ copied ? "Copied" : "Copy code" }}</button>
      <button type="button" class="primary" @click="emit('done')">{{ buttonLabel }}</button>
    </div>
    <p class="section-note">Keep it in a password manager, separately from anything that shows what this account is for.</p>
  </section>
</template>
