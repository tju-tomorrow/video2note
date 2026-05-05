<script setup lang="ts">
import { computed, onMounted, ref, type Component } from "vue";
import {
  Archive,
  FileText,
  Layers3,
  MessageSquare,
  Moon,
  Plus,
  Search,
  Settings,
  Sparkles,
  Sun,
} from "lucide-vue-next";
import { RouterLink, RouterView, useRouter } from "vue-router";
import { useRoute } from "vue-router";
import WindowChrome from "./components/WindowChrome.vue";

const isMac = computed(() => window.appMeta?.platform === "darwin");
const route = useRoute();
const router = useRouter();

const theme = ref<"dark" | "light">("light");

function toggleTheme() {
  theme.value = theme.value === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", theme.value);
}

onMounted(() => {
  document.documentElement.setAttribute("data-theme", "light");
  if (window.appMeta?.platform === "darwin") {
    document.documentElement.classList.add("platform-mac");
  }
});

const NAV_ITEMS = [
  {
    name: "extract",
    label: "单条提取",
    icon: FileText,
    ready: true,
  },
  {
    name: "batch",
    label: "视频搜索",
    icon: Search,
    ready: true,
  },
  {
    name: "library",
    label: "素材库",
    icon: Archive,
    ready: true,
  },
  {
    name: "chat",
    label: "Agent聊天",
    icon: MessageSquare,
    ready: true,
  },
  {
    name: "settings",
    label: "设置",
    icon: Settings,
    ready: false,
  },
] as const satisfies ReadonlyArray<{
  name: string;
  label: string;
  icon: Component;
  ready: boolean;
}>;

const currentTitle = computed(() => (route.meta.navTitle as string) || "工作台");
const currentDescription = computed(
  () => (route.meta.navDescription as string) || "本地视频文案工作流",
);

function newTask() {
  router.push({ name: "extract" });
}
</script>

<template>
  <div class="app-root">
    <WindowChrome v-if="isMac" title="VideoExtract2Note" />

    <div class="app-frame" :class="{ 'app-frame--mac': isMac }">
      <aside class="sidebar" aria-label="功能导航">
        <div class="sidebar__brand">
          <div class="brand-mark">
            <img src="/icon.png" alt="VideoExtract" width="32" height="32" />
          </div>
          <div class="sidebar__brand-text">
            <strong>VideoExtract</strong>
            <span>文案工作流</span>
          </div>
        </div>

        <button type="button" class="new-task-btn" @click="newTask">
          <Plus :size="15" aria-hidden="true" />
          新任务
        </button>

        <nav class="sidebar__nav">
          <template v-for="item in NAV_ITEMS" :key="item.name">
            <RouterLink
              v-if="item.ready"
              :to="{ name: item.name }"
              class="nav-item"
              active-class="nav-item--active"
            >
              <component :is="item.icon" :size="16" aria-hidden="true" />
              <span>{{ item.label }}</span>
            </RouterLink>
            <span
              v-else
              class="nav-item nav-item--disabled"
              :title="'尚未实现：' + item.label"
            >
              <component :is="item.icon" :size="16" aria-hidden="true" />
              <span>{{ item.label }}</span>
              <small class="nav-item__badge">Soon</small>
            </span>
          </template>
        </nav>

        <div class="sidebar__footer">
          <Sparkles :size="14" aria-hidden="true" class="sidebar__footer-icon" />
          <span>本地引擎</span>
          <strong>Ready</strong>
          <button
            type="button"
            class="theme-toggle"
            :title="theme === 'dark' ? '切换亮色' : '切换暗色'"
            @click="toggleTheme"
          >
            <Sun v-if="theme === 'dark'" :size="14" aria-hidden="true" />
            <Moon v-else :size="14" aria-hidden="true" />
          </button>
        </div>
      </aside>

      <main class="main-area">
        <header class="topbar">
          <div>
            <h1>{{ currentTitle }}</h1>
            <p>{{ currentDescription }}</p>
          </div>
          <div class="topbar__actions" aria-label="全局操作">
            <button type="button" class="icon-button" title="同步历史记录" disabled>
              <Archive :size="16" aria-hidden="true" />
            </button>
            <button type="button" class="icon-button" title="打开设置" disabled>
              <Settings :size="16" aria-hidden="true" />
            </button>
          </div>
        </header>
        <RouterView v-slot="{ Component }">
          <Transition name="route-fade" mode="out-in">
            <component :is="Component" />
          </Transition>
        </RouterView>
      </main>
    </div>
  </div>
</template>
