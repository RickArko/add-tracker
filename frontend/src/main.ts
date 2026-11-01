import "@fontsource-variable/atkinson-hyperlegible-next";
import { createApp } from "vue";
import App from "./App.vue";
import { setUnauthorizedHandler } from "./lib/api";
import { auth } from "./lib/auth";
import { router } from "./router";
import "./style.css";

setUnauthorizedHandler(() => {
  auth.username = null;
  void router.push("/login");
});

createApp(App).use(router).mount("#app");
