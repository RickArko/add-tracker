import { reactive } from "vue";
import { api } from "./api";

export const auth = reactive({
  loaded: false,
  username: null as string | null,
  signupOpen: false,
  firstRun: false,
});

export async function loadAuth() {
  const status = await api<{ user: { username: string } | null; signup_open: boolean; first_run: boolean }>(
    "/api/auth/status",
  );
  auth.username = status.user?.username ?? null;
  auth.signupOpen = status.signup_open;
  auth.firstRun = status.first_run;
  auth.loaded = true;
}
