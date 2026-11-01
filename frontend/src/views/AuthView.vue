<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import TallyMarks from "../components/TallyMarks.vue";
import { api, ApiError, USERNAME_RULE } from "../lib/api";
import { auth, loadAuth } from "../lib/auth";

const router = useRouter();
const mode = ref<"login" | "register">(auth.firstRun && auth.signupOpen ? "register" : "login");
const username = ref("");
const password = ref("");
const error = ref("");
const busy = ref(false);
const registering = computed(() => mode.value === "register");
const usernameInvalid = computed(
  () => registering.value && username.value.trim() !== "" && !/^[a-zA-Z0-9_.-]{3,40}$/.test(username.value.trim()),
);

async function submit() {
  if (usernameInvalid.value) return;
  busy.value = true;
  error.value = "";
  try {
    await api(`/api/auth/${mode.value}`, "POST", {
      username: username.value,
      password: password.value,
    });
    password.value = "";
    await loadAuth();
    await router.push("/");
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "That didn't work. Try again.";
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="auth page">
    <TallyMarks :count="5" />
    <h1>Habit Helper</h1>
    <p class="lede">Count what you use. See the pattern. Change it at your own pace.</p>

    <form @submit.prevent="submit">
      <label class="field">
        <span>Username</span>
        <input
          v-model="username"
          required
          :minlength="registering ? 3 : undefined"
          maxlength="40"
          autocomplete="username"
          autocapitalize="none"
          spellcheck="false"
        />
        <small v-if="usernameInvalid" class="error" role="alert">{{ USERNAME_RULE }}</small>
        <small v-else-if="registering">Doesn't need to be your name, and an email address won't work here.</small>
      </label>
      <label class="field">
        <span>Passphrase</span>
        <input
          v-model="password"
          type="password"
          required
          :minlength="registering ? 10 : undefined"
          maxlength="200"
          :autocomplete="registering ? 'new-password' : 'current-password'"
        />
        <small v-if="registering">At least 10 characters. Save it in a password manager, because there's no email reset.</small>
      </label>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <button class="primary wide" type="submit" :disabled="busy">
        {{ registering ? "Create account" : "Log in" }}
      </button>
    </form>

    <p v-if="auth.signupOpen">
      <button class="link" type="button" @click="mode = registering ? 'login' : 'register'">
        {{ registering ? "Log in to an existing account" : "Create an account" }}
      </button>
    </p>
    <p><RouterLink to="/help">Need support right now?</RouterLink></p>
  </div>
</template>
