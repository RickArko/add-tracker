<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import RecoveryCodeNotice from "../components/RecoveryCodeNotice.vue";
import TallyMarks from "../components/TallyMarks.vue";
import { api, ApiError, USERNAME_RULE } from "../lib/api";
import { auth, loadAuth } from "../lib/auth";

const router = useRouter();
const route = useRoute();
const mode = ref<"login" | "register" | "recover" | "email">(
  auth.firstRun && auth.signupOpen ? "register" : "login",
);
const username = ref("");
const password = ref("");
const code = ref("");
const email = ref("");
const error = ref("");
const message = ref("");
const busy = ref(false);
const newCode = ref("");
const registering = computed(() => mode.value === "register");
const usernameInvalid = computed(
  () => registering.value && username.value.trim() !== "" && !/^[a-zA-Z0-9_.-]{3,40}$/.test(username.value.trim()),
);
const signingIn = computed(() => mode.value === "login" || mode.value === "register");

function show(next: typeof mode.value) {
  mode.value = next;
  error.value = "";
  message.value = "";
}

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

async function finish() {
  newCode.value = "";
  await loadAuth();
  // Internal paths only, so a crafted link can't send someone to another site after log in.
  const next = String(route.query.next ?? "");
  await router.push(next.startsWith("/") && !next.startsWith("//") ? next : "/");
}

const submit = () =>
  attempt(async () => {
    if (usernameInvalid.value) return;
    const result = await api<{ recovery_code?: string }>(`/api/auth/${mode.value}`, "POST", {
      username: username.value,
      password: password.value,
    });
    password.value = "";
    if (result.recovery_code) newCode.value = result.recovery_code;
    else await finish();
  });

const recover = () =>
  attempt(async () => {
    const result = await api<{ recovery_code: string }>("/api/auth/recover", "POST", {
      username: username.value,
      recovery_code: code.value,
      new_password: password.value,
    });
    password.value = "";
    code.value = "";
    newCode.value = result.recovery_code;
  });

const requestEmail = () =>
  attempt(async () => {
    await api("/api/auth/email/reset-request", "POST", { email: email.value });
    message.value = "If that email is on an account, a reset link is on its way. It works for 30 minutes.";
  });
</script>

<template>
  <div class="auth page">
    <RecoveryCodeNotice v-if="newCode" :code="newCode" button-label="I've saved it" @done="finish" />
    <template v-else>
      <TallyMarks :count="5" />
      <h1>Habit Helper</h1>
      <p class="lede">Count what you use. See the pattern. Change it at your own pace.</p>

      <form v-if="signingIn" @submit.prevent="submit">
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
          <small v-if="registering">At least 10 characters. You'll get a recovery code next, in case you forget it.</small>
        </label>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <button class="primary wide" type="submit" :disabled="busy">
          {{ registering ? "Create account" : "Log in" }}
        </button>
      </form>

      <form v-else-if="mode === 'recover'" @submit.prevent="recover">
        <h2>Use your recovery code</h2>
        <label class="field">
          <span>Username</span>
          <input v-model="username" required maxlength="40" autocomplete="username" autocapitalize="none" spellcheck="false" />
        </label>
        <label class="field">
          <span>Recovery code</span>
          <input v-model="code" required maxlength="60" autocomplete="off" autocapitalize="characters" spellcheck="false" />
        </label>
        <label class="field">
          <span>New passphrase</span>
          <input v-model="password" type="password" required minlength="10" maxlength="200" autocomplete="new-password" />
        </label>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <button class="primary wide" type="submit" :disabled="busy">Set new passphrase</button>
      </form>

      <form v-else @submit.prevent="requestEmail">
        <h2>Reset by email</h2>
        <p>This only works if you added and confirmed an email in Settings.</p>
        <label class="field">
          <span>Email</span>
          <input v-model="email" type="email" required maxlength="254" autocomplete="email" />
        </label>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <p v-if="message" role="status">{{ message }}</p>
        <button class="primary wide" type="submit" :disabled="busy">Send reset link</button>
      </form>

      <div class="auth-links">
        <button v-if="!signingIn" class="link" type="button" @click="show('login')">Back to log in</button>
        <button v-if="mode === 'login'" class="link" type="button" @click="show('recover')">Forgot your passphrase?</button>
        <button v-if="mode === 'email'" class="link" type="button" @click="show('recover')">Use a recovery code instead</button>
        <button v-if="mode === 'recover' && auth.emailEnabled" class="link" type="button" @click="show('email')">Reset by email instead</button>
        <button v-if="auth.signupOpen && registering" class="link" type="button" @click="show('login')">Log in to an existing account</button>
        <button v-if="auth.signupOpen && mode === 'login'" class="link" type="button" @click="show('register')">Create an account</button>
        <RouterLink to="/help">Need support right now?</RouterLink>
      </div>
    </template>
  </div>
</template>
