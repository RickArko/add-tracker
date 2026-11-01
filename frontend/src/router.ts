import { createRouter, createWebHistory } from "vue-router";
import { loadAuth, auth } from "./lib/auth";
import AuthView from "./views/AuthView.vue";
import HelpView from "./views/HelpView.vue";
import HistoryView from "./views/HistoryView.vue";
import SettingsView from "./views/SettingsView.vue";
import TodayView from "./views/TodayView.vue";
import TrendsView from "./views/TrendsView.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: TodayView, meta: { title: "Today" } },
    { path: "/trends", component: TrendsView, meta: { title: "Trends" } },
    { path: "/history", component: HistoryView, meta: { title: "History" } },
    { path: "/settings", component: SettingsView, meta: { title: "Settings" } },
    { path: "/help", component: HelpView, meta: { title: "Get support", public: true } },
    { path: "/login", component: AuthView, meta: { title: "Log in", public: true } },
    { path: "/:rest(.*)", redirect: "/" },
  ],
});

router.beforeEach(async (to) => {
  if (!auth.loaded) await loadAuth().catch(() => {});
  if (!auth.username && !to.meta.public) return "/login";
  if (auth.username && to.path === "/login") return "/";
});

router.afterEach((to) => {
  document.title = `${to.meta.title} | Habit Helper`;
});
