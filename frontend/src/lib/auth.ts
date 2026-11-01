import { reactive } from "vue";
import { api, ApiError } from "./api";

const USER_KEY = "tally.user";

export const auth = reactive({
  loaded: false,
  username: null as string | null,
  signupOpen: false,
  firstRun: false,
  emailEnabled: false,
  hasRecoveryCode: true,
  hasEmail: false,
});

export async function loadAuth() {
  try {
    const status = await api<{
      user: { username: string; has_recovery_code: boolean; has_email: boolean } | null;
      signup_open: boolean;
      first_run: boolean;
      email_enabled: boolean;
    }>("/api/auth/status");
    auth.username = status.user?.username ?? null;
    auth.signupOpen = status.signup_open;
    auth.firstRun = status.first_run;
    auth.emailEnabled = status.email_enabled;
    auth.hasRecoveryCode = status.user?.has_recovery_code ?? true;
    auth.hasEmail = status.user?.has_email ?? false;
    if (auth.username) localStorage.setItem(USER_KEY, auth.username);
    else localStorage.removeItem(USER_KEY);
  } catch (error) {
    // With no signal, carry on as the last user so logging still works.
    if (!(error instanceof ApiError) || error.status === 0 || error.status >= 500) {
      auth.username = localStorage.getItem(USER_KEY);
    } else {
      throw error;
    }
  }
  auth.loaded = true;
}
