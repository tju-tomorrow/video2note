import { createRouter, createWebHashHistory } from "vue-router";
import ExtractView from "../views/ExtractView.vue";
import HistoryView from "../views/HistoryView.vue";
import SearchView from "../views/SearchView.vue";
import ChatView from "../views/ChatView.vue";
import PlaceholderView from "../views/PlaceholderView.vue";

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/", redirect: "/extract" },
    {
      path: "/extract",
      name: "extract",
      component: ExtractView,
      meta: {
        navTitle: "单条提取",
        navDescription: "链接转文案",
        ready: true,
      },
    },
    {
      path: "/batch",
      name: "batch",
      component: SearchView,
      meta: {
        navTitle: "视频搜索",
        navDescription: "搜索抖音/B站视频并提取文案",
        ready: true,
      },
    },
    {
      path: "/history",
      name: "library",
      component: HistoryView,
      meta: {
        navTitle: "素材库",
        navDescription: "历史记录与搜索",
        ready: true,
      },
    },
    {
      path: "/chat",
      name: "chat",
      component: ChatView,
      meta: {
        navTitle: "Agent聊天",
        navDescription: "基于转写内容与AI对话",
        ready: true,
      },
    },
    {
      path: "/automation",
      name: "automation",
      component: PlaceholderView,
      meta: {
        navTitle: "自动整理",
        navDescription: "规则与模板",
        ready: false,
        placeholderKicker: "RULES",
        placeholderHint: "后续可按账号、关键词或模板自动整理文案，并输出到笔记格式。",
      },
    },
    {
      path: "/settings",
      name: "settings",
      component: PlaceholderView,
      meta: {
        navTitle: "设置",
        navDescription: "模型与路径",
        ready: false,
        placeholderKicker: "CONFIG",
        placeholderHint: "模型选择、下载目录、代理、浏览器策略和快捷键会集中到这里。",
      },
    },
    { path: "/:pathMatch(.*)*", redirect: "/extract" },
  ],
});
