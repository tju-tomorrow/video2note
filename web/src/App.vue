<script setup lang="ts">
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

const route = useRoute();
const router = useRouter();

const isAppPage = () => route.name !== "landing";

const NAV_ITEMS = [
  { name: "extract", label: "单条提取", icon: FileText, ready: true },
  { name: "history", label: "素材库", icon: Archive, ready: true },
  { name: "chat", label: "Agent聊天", icon: MessageSquare, ready: true },
];

function newTask() {
  router.push({ name: "extract" });
}
</script>

<template>
  <div class="app-root">
    <!-- Landing 页：全屏无导航 -->
    <template v-if="!isAppPage()">
      <RouterView v-slot="{ Component }">
        <component :is="Component" />
      </RouterView>
    </template>

    <!-- App 页：侧边栏 + 主区域 -->
    <div v-else class="app-frame">
      <aside class="sidebar" aria-label="功能导航">
        <div class="sidebar__brand">
          <div class="brand-mark">
            <img src="/icon.png" alt="VidWise" width="32" height="32" />
          </div>
          <div class="sidebar__brand-text">
            <strong>VidWise</strong>
            <span>视频文案工作流</span>
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
          <span>Web 版</span>
          <strong>Beta</strong>
        </div>
      </aside>

      <main class="main-area">
        <RouterView v-slot="{ Component }">
          <Transition name="route-fade" mode="out-in">
            <component :is="Component" />
          </Transition>
        </RouterView>
      </main>
    </div>
  </div>
</template>
