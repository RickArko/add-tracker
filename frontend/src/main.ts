import "@fontsource-variable/atkinson-hyperlegible-next";
import { createApp } from "vue";
import App from "./App.vue";
import { setUnauthorizedHandler } from "./lib/api";
import { auth } from "./lib/auth";
import { router } from "./router";
import "./style.css";

setUnauthorizedHandler(() => {
  // Drops the saved Today view if a session ends elsewhere. Unsent logs wait for the next log in.
  if (auth.username) localStorage.removeItem(`tally.today.${auth.username}`);
  auth.username = null;
  void router.push("/login");
});

createApp(App).use(router).mount("#app");

if (import.meta.env.PROD && "serviceWorker" in navigator) {
  // Offline support is a bonus, so a failed registration shouldn't surface as an error.
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
