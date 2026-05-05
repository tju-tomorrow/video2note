<script setup lang="ts">
import { computed } from "vue";
import { LockKeyhole, Sparkles } from "lucide-vue-next";
import { useRoute } from "vue-router";

const route = useRoute();

const title = computed(() => (route.meta.navTitle as string) || "页面");
const hint = computed(() => (route.meta.placeholderHint as string) || "");
const kicker = computed(() => (route.meta.placeholderKicker as string) || "SOON");
</script>

<template>
  <div class="placeholder-page">
    <section class="workspace-panel placeholder-panel">
      <div class="placeholder-lock">
        <LockKeyhole :size="22" aria-hidden="true" />
      </div>
      <p class="panel-kicker">{{ kicker }}</p>
      <h2>{{ title }}</h2>
      <p v-if="hint">{{ hint }}</p>
      <div class="placeholder-actions">
        <button type="button" class="primary" disabled>
          <Sparkles :size="16" aria-hidden="true" />
          等待接入
        </button>
      </div>
    </section>

    <section class="placeholder-grid" aria-label="未实现功能预览">
      <div class="ghost-feature">
        <strong>任务状态</strong>
        <span>Locked</span>
      </div>
      <div class="ghost-feature">
        <strong>导出动作</strong>
        <span>Locked</span>
      </div>
      <div class="ghost-feature">
        <strong>本地配置</strong>
        <span>Locked</span>
      </div>
    </section>
  </div>
</template>
