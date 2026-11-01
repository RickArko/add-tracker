<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import RecoveryCodeNotice from "../components/RecoveryCodeNotice.vue";
import { api, ApiError } from "../lib/api";
import { auth, loadAuth } from "../lib/auth";

const props = defineProps<{ kind: "reset" | "confirm" }>();
const route = useRoute();
const router = useRouter();
const token = String(route.query.token ?? "");
const password = ref("");
const error = ref("");
const done = ref(false);
const busy = ref(false);
const newCode = ref("");
const loginLink = computed(() => ({
  path: "/login",
  query: { next: `/confirm-email?token=${encodeURIComponent(token)}` },
}));

async function attempt(action: () => Promise<void>) {
  busy.value = true;
  error.value = "";
  try {
    await action();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "That didn't work. Try again.";
  } finally {
    busy.value = false;
  }
}

const reset = () =>
  attempt(async () => {
    const result = await api<{ recovery_code: string }>("/api/auth/email/reset", "POST", {
      token,
      new_password: password.value,
    });
    password.value = "";
    newCode.value = result.recovery_code;
  });

// A person has to press the button, so a mail scanner opening the link changes nothing.
const confirmEmail = () =>
  attempt(async () => {
    await api("/api/auth/email/confirm", "POST", { token });
    done.value = true;
    await loadAuth();
  });

async function finish() {
  await loadAuth();
  await router.push("/");
}

// Takes the secret out of the address bar and browser history.
onMounted(() => {
  if (window.location.search) window.history.replaceState(window.history.state, "", window.location.pathname);
});
</script>

<template>
  <div class="page auth">
    <RecoveryCodeNotice v-if="newCode" :code="newCode" button-label="I've saved it" @done="finish" />
    <template v-else-if="kind === 'reset'">
      <h1>Set a new passphrase</h1>
      <form @submit.prevent="reset">
        <label class="field">
          <span>New passphrase</span>
          <input v-model="password" type="password" required minlength="10" maxlength="200" autocomplete="new-password" />
          <small>At least 10 characters. This logs out your other devices and replaces your recovery code.</small>
        </label>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <button class="primary wide" type="submit" :disabled="busy">Set new passphrase</button>
      </form>
    </template>
    <template v-else>
      <h1>Confirm email</h1>
      <p v-if="done" role="status">Your email is confirmed. You can use it to reset your passphrase.</p>
      <template v-else-if="auth.username">
        <p>Use this address to recover <strong>{{ auth.username }}</strong>?</p>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <button class="primary wide" type="button" :disabled="busy" @click="confirmEmail">Confirm email</button>
      </template>
      <template v-else>
        <p>Log in to the account that asked for this link to confirm it.</p>
        <RouterLink class="button primary" :to="loginLink">Log in</RouterLink>
      </template>
    </template>
    <p v-if="!newCode"><RouterLink to="/">Back to the app</RouterLink></p>
  </div>
</template>
