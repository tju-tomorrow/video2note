import { createRouter, createWebHistory } from "vue-router";
import LandingView from "../views/LandingView.vue";
import ExtractView from "../views/ExtractView.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "landing", component: LandingView },
    { path: "/extract", name: "extract", component: ExtractView },
    {
      path: "/history",
      name: "history",
      component: () => import("../views/HistoryView.vue"),
    },
    {
      path: "/chat",
      name: "chat",
      component: () => import("../views/ChatView.vue"),
    },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});
