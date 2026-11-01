<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import PlanForm from "../components/PlanForm.vue";
import TrackerForm from "../components/TrackerForm.vue";
import { api, ApiError, type Tracker } from "../lib/api";
import { auth, loadAuth } from "../lib/auth";
import { goalLabel } from "../lib/catalog";
import { fullDate, quantity } from "../lib/format";
import { clearLocalData, flushQueue, getQueue } from "../lib/offline";

const router = useRouter();
const trackers = ref<Tracker[]>([]);
const adding = ref(false);
const planFor = ref<number | null>(null);
const NO_LEVELS = ["alcohol", "benzodiazepine", "opioid"];
const editingId = ref<number | null>(null);
const confirmDelete = ref<number | null>(null);
const error = ref("");

const currentPassword = ref("");
const newPassword = ref("");
const passwordMessage = ref("");
const passwordError = ref("");

const deletePassword = ref("");
const deleteError = ref("");

function message(e: unknown, fallback: string) {
  return e instanceof ApiError ? e.message : fallback;
}

async function load() {
  try {
    trackers.value = await api<Tracker[]>("/api/trackers?include_archived=true");
  } catch (e) {
    error.value = message(e, "Settings didn't load.");
  }
}

async function saved() {
  adding.value = false;
  editingId.value = null;
  planFor.value = null;
  await load();
}

async function removePlan(tracker: Tracker) {
  error.value = "";
  try {
    await api(`/api/trackers/${tracker.id}/plan`, "DELETE");
    await load();
  } catch (e) {
    error.value = message(e, "That didn't save. Try again.");
  }
}

async function setArchived(tracker: Tracker, archived: boolean) {
  error.value = "";
  try {
    await api(`/api/trackers/${tracker.id}`, "PATCH", { archived });
    await load();
  } catch (e) {
    error.value = message(e, "That didn't save. Try again.");
  }
}

async function removeTracker(tracker: Tracker) {
  error.value = "";
  try {
    await api(`/api/trackers/${tracker.id}`, "DELETE");
    confirmDelete.value = null;
    await load();
  } catch (e) {
    error.value = message(e, "That wasn't deleted. Try again.");
  }
}

async function changePassword() {
  passwordMessage.value = "";
  passwordError.value = "";
  try {
    await api("/api/auth/password", "POST", {
      current_password: currentPassword.value,
      new_password: newPassword.value,
    });
    currentPassword.value = "";
    newPassword.value = "";
    passwordMessage.value = "Passphrase changed. Other devices were logged out.";
  } catch (e) {
    passwordError.value = message(e, "The passphrase wasn't changed. Try again.");
  }
}

async function logout() {
  error.value = "";
  try {
    await flushQueue();
    if (getQueue().length) {
      error.value = "Some logs are still waiting to send. Reconnect before you log out, so they aren't lost.";
      window.scrollTo(0, 0);
      return;
    }
    await api("/api/auth/logout", "POST");
  } catch (e) {
    error.value = message(e, "You're still logged in. Try again.");
    window.scrollTo(0, 0);
    return;
  }
  clearLocalData();
  auth.username = null;
  await loadAuth().catch(() => {});
  await router.push("/login");
}

async function deleteAccount() {
  deleteError.value = "";
  try {
    await api("/api/auth/account", "DELETE", { password: deletePassword.value });
    clearLocalData();
    auth.username = null;
    await loadAuth().catch(() => {});
    await router.push("/login");
  } catch (e) {
    deleteError.value = message(e, "The account wasn't deleted. Try again.");
  }
}

onMounted(load);
</script>

<template>
  <div class="page settings">
    <h1>Settings</h1>
    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <section>
      <h2>What you track</h2>
      <ul class="tracker-list">
        <li v-for="t in trackers" :key="t.id" :data-tracker="t.name">
          <TrackerForm v-if="editingId === t.id" :tracker="t" @saved="saved" @cancel="editingId = null" />
          <template v-else>
            <div>
              <strong>{{ t.name }}</strong>
              <small v-if="t.archived_at">Hidden from Today. History is kept.</small>
              <small v-else-if="t.stopped_on">Stopped {{ fullDate(t.stopped_on) }}</small>
              <small v-else>
                {{ goalLabel(t.goal) }}<template v-if="t.daily_limit !== null">, limit {{ quantity(t.daily_limit, t.unit) }} a day</template>
              </small>
              <small v-if="t.step_amount">Levels on: down {{ quantity(t.step_amount, t.unit) }} after {{ t.clear_days }} days cleared</small>
            </div>
            <div class="row-actions">
              <button type="button" class="quiet" @click="editingId = t.id">Edit</button>
              <button v-if="!NO_LEVELS.includes(t.category) && !t.stopped_on" type="button" class="quiet" @click="planFor = t.id">{{ t.step_amount ? "Change levels" : "Set up levels" }}</button>
              <button v-if="t.step_amount" type="button" class="quiet" @click="removePlan(t)">Turn off levels</button>
              <button v-if="t.archived_at" type="button" class="quiet" @click="setArchived(t, false)">Show on Today</button>
              <button v-else type="button" class="quiet" @click="setArchived(t, true)">Hide</button>
              <button v-if="confirmDelete !== t.id" type="button" class="quiet" @click="confirmDelete = t.id">Delete</button>
              <template v-else>
                <button type="button" class="danger" @click="removeTracker(t)">Delete {{ t.name }} and its history</button>
                <button type="button" class="quiet" @click="confirmDelete = null">Keep</button>
              </template>
            </div>
          </template>
          <div v-if="planFor === t.id" class="tracker-plan">
            <PlanForm :tracker="t" @saved="saved" @cancel="planFor = null" />
          </div>
        </li>
      </ul>
      <TrackerForm v-if="adding" @saved="saved" />
      <button v-else type="button" class="secondary" @click="adding = true">Add something to track</button>
    </section>

    <section>
      <h2>Your data</h2>
      <p>Your logs are stored only on this server, under your account. This app has no ads, analytics or outside services, and nothing is sent to anyone else.</p>
      <p class="row-actions">
        <a class="button secondary" href="/api/export.csv" download>Download as CSV</a>
        <a class="button secondary" href="/api/export.json" download>Download as JSON</a>
      </p>
    </section>

    <section>
      <h2>Passphrase</h2>
      <form @submit.prevent="changePassword">
        <input class="visually-hidden" tabindex="-1" aria-hidden="true" autocomplete="username" :value="auth.username ?? ''" readonly />
        <label class="field">
          <span>Current passphrase</span>
          <input v-model="currentPassword" type="password" required autocomplete="current-password" />
        </label>
        <label class="field">
          <span>New passphrase</span>
          <input v-model="newPassword" type="password" required minlength="10" maxlength="200" autocomplete="new-password" />
        </label>
        <p v-if="passwordError" class="error" role="alert">{{ passwordError }}</p>
        <p v-if="passwordMessage" role="status">{{ passwordMessage }}</p>
        <button class="secondary" type="submit">Change passphrase</button>
      </form>
    </section>

    <section>
      <h2>Account</h2>
      <p>Logged in as <strong>{{ auth.username }}</strong>.</p>
      <button type="button" class="secondary" @click="logout">Log out</button>

      <details class="danger-zone">
        <summary>Delete account</summary>
        <p>This permanently removes your account and every log. It can't be undone, so download a copy first if you want one.</p>
        <form @submit.prevent="deleteAccount">
          <label class="field">
            <span>Enter your passphrase to confirm</span>
            <input v-model="deletePassword" type="password" required autocomplete="current-password" />
          </label>
          <p v-if="deleteError" class="error" role="alert">{{ deleteError }}</p>
          <button class="danger" type="submit">Delete my account and all logs</button>
        </form>
      </details>
    </section>

    <p class="footer-links"><RouterLink to="/help">Get support</RouterLink></p>
  </div>
</template>
