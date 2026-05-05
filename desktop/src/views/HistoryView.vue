<script setup lang="ts">
import { ref, onMounted } from "vue";
import {
  Archive,
  Copy,
  ExternalLink,
  FileText,
  Globe,
  Loader2,
  Search,
  Video,
  X,
} from "lucide-vue-next";

const records = ref<RecordItem[]>([]);
const loading = ref(false);
const searchQuery = ref("");
const searchMode = ref(false);
const selectedRecord = ref<RecordDetail | null>(null);
const detailLoading = ref(false);
const copyFeedback = ref("");
const error = ref("");

async function loadHistory() {
  const bridge = window.desktopBridge;
  if (!bridge) return;
  loading.value = true;
  error.value = "";
  try {
    const res = await bridge.listHistory(50, 0);
    if (res.ok) {
      records.value = res.records;
    } else {
      error.value = res.error || "加载失败";
    }
  } catch (e) {
    error.value = String(e);
  } finally {
    loading.value = false;
  }
}

async function doSearch() {
  const bridge = window.desktopBridge;
  if (!bridge) return;
  const q = searchQuery.value.trim();
  if (!q) {
    searchMode.value = false;
    await loadHistory();
    return;
  }
  loading.value = true;
  searchMode.value = true;
  error.value = "";
  try {
    const res = await bridge.searchRecords(q, 20);
    if (res.ok) {
      records.value = res.records;
    } else {
      error.value = res.error || "搜索失败";
    }
  } catch (e) {
    error.value = String(e);
  } finally {
    loading.value = false;
  }
}

function clearSearch() {
  searchQuery.value = "";
  searchMode.value = false;
  loadHistory();
}

async function viewDetail(id: number) {
  const bridge = window.desktopBridge;
  if (!bridge) return;
  detailLoading.value = true;
  try {
    const res = await bridge.getRecord(id);
    if (res.ok && res.record) {
      selectedRecord.value = res.record;
    }
  } finally {
    detailLoading.value = false;
  }
}

function closeDetail() {
  selectedRecord.value = null;
  copyFeedback.value = "";
}

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    copyFeedback.value = "已复制";
    setTimeout(() => (copyFeedback.value = ""), 2000);
  } catch {
    copyFeedback.value = "复制失败";
  }
}

function platformIcon(p: string) {
  if (p === "douyin" || p === "bilibili") return Video;
  return Globe;
}

function platformLabel(p: string) {
  if (p === "douyin") return "抖音";
  if (p === "bilibili") return "B站";
  if (p === "web") return "网页";
  return p || "未知";
}

function truncate(s: string, n: number) {
  return s.length > n ? s.slice(0, n) + "..." : s;
}

onMounted(loadHistory);
</script>

<template>
  <div class="history-page">
    <!-- 搜索栏 -->
    <div class="search-bar">
      <Search :size="15" aria-hidden="true" class="search-icon" />
      <input
        v-model="searchQuery"
        type="text"
        placeholder="搜索历史记录..."
        @keydown.enter="doSearch"
      />
      <button
        v-if="searchQuery"
        type="button"
        class="search-clear"
        @click="clearSearch"
      >
        <X :size="14" aria-hidden="true" />
      </button>
    </div>

    <!-- 状态提示 -->
    <div class="history-status">
      <span v-if="searchMode">{{ records.length }} 条搜索结果</span>
      <span v-else>{{ records.length }} 条记录</span>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="history-empty">
      <Loader2 :size="20" class="spin" aria-hidden="true" />
      <span>加载中...</span>
    </div>

    <!-- 错误 -->
    <div v-else-if="error" class="history-error">{{ error }}</div>

    <!-- 空状态 -->
    <div v-else-if="!records.length" class="history-empty">
      <FileText :size="28" aria-hidden="true" />
      <p>{{ searchMode ? "未找到匹配记录" : "暂无历史记录" }}</p>
      <p class="history-empty__hint">
        {{ searchMode ? "换个关键词试试" : "使用「单条提取」后会自动保存到这里" }}
      </p>
    </div>

    <!-- 记录列表 -->
    <ul v-else class="record-list">
      <li
        v-for="r in records"
        :key="r.id"
        class="record-item"
        :class="{ 'record-item--active': selectedRecord?.id === r.id }"
        @click="viewDetail(r.id)"
      >
        <div class="record-item__icon">
          <component :is="platformIcon(r.platform)" :size="15" aria-hidden="true" />
        </div>
        <div class="record-item__body">
          <div class="record-item__head">
            <strong>{{ r.title || "(无标题)" }}</strong>
            <span class="record-item__platform">{{ platformLabel(r.platform) }}</span>
            <span v-if="r.engine" class="record-item__engine">{{ r.engine }}</span>
          </div>
          <p class="record-item__preview">{{ truncate(r.preview, 140) }}</p>
          <div class="record-item__meta">
            <span>{{ r.createdAt }}</span>
            <a
              :href="r.url"
              target="_blank"
              rel="noopener"
              class="record-item__link"
              @click.stop
            >
              <ExternalLink :size="11" aria-hidden="true" />
              原链接
            </a>
          </div>
        </div>
      </li>
    </ul>

    <!-- 详情弹层 -->
    <Transition name="slide-up">
      <div v-if="selectedRecord" class="detail-overlay" @click.self="closeDetail">
        <div class="detail-card">
          <div class="detail-card__head">
            <div>
              <strong>{{ selectedRecord.title || "(无标题)" }}</strong>
              <div class="detail-meta">
                <span>{{ platformLabel(selectedRecord.platform) }}</span>
                <span v-if="selectedRecord.engine">{{ selectedRecord.engine }}</span>
                <span v-if="selectedRecord.duration">{{ Math.round(selectedRecord.duration) }}s</span>
                <span>{{ selectedRecord.createdAt }}</span>
              </div>
            </div>
            <div class="detail-card__actions">
              <button type="button" class="ghost" @click="copyText(selectedRecord!.formattedText)">
                <Copy :size="14" aria-hidden="true" />
                {{ copyFeedback || "复制" }}
              </button>
              <button type="button" class="ghost" @click="closeDetail">
                <X :size="15" aria-hidden="true" />
              </button>
            </div>
          </div>
          <div v-if="detailLoading" class="detail-card__loading">
            <Loader2 :size="18" class="spin" aria-hidden="true" />
          </div>
          <div v-else class="detail-card__body">
            {{ selectedRecord.formattedText }}
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.history-page {
}

/* ── Search ──────────────────────────────────────────────────────── */
.search-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--surface-muted);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  transition: border-color 0.15s, box-shadow 0.15s;
}

.search-bar:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.search-bar input {
  flex: 1;
  border: none;
  background: transparent;
  font-size: 14px;
  outline: none;
  color: var(--ink);
  padding: 4px 0;
}

.search-bar input::placeholder {
  color: var(--ink-muted);
}

.search-icon {
  color: var(--ink-muted);
  flex-shrink: 0;
}

.search-clear {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: none;
  border-radius: 4px;
  color: var(--ink-muted);
  background: transparent;
  cursor: pointer;
}

.search-clear:hover {
  color: var(--ink);
  background: var(--line);
}

/* ── Status ──────────────────────────────────────────────────────── */
.history-status {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 4px 8px;
  font-size: 12px;
  color: var(--ink-muted);
  font-weight: 500;
}

/* ── Empty & Error ───────────────────────────────────────────────── */
.history-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 60px 16px;
  color: var(--ink-muted);
  text-align: center;
}

.history-empty p {
  margin: 0;
  font-size: 14px;
}

.history-empty__hint {
  font-size: 13px;
  opacity: 0.65;
}

.history-error {
  padding: 24px 0;
  color: var(--danger);
  font-size: 14px;
}

/* ── Record List ─────────────────────────────────────────────────── */
.record-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.record-item {
  display: flex;
  gap: 12px;
  padding: 14px 4px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.12s;
}

.record-item:hover {
  background: var(--surface-muted);
}

.record-item--active {
  background: var(--accent-soft);
}

.record-item__icon {
  width: 34px;
  height: 34px;
  border-radius: var(--radius-sm);
  background: var(--surface-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--ink-soft);
  margin-top: 2px;
}

.record-item__body {
  flex: 1;
  min-width: 0;
}

.record-item__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 3px;
}

.record-item__head strong {
  font-size: 14px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.record-item__platform,
.record-item__engine {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--surface-muted);
  color: var(--ink-muted);
  flex-shrink: 0;
  font-weight: 500;
}

.record-item__preview {
  font-size: 13px;
  color: var(--ink-soft);
  line-height: 1.55;
  margin: 0 0 4px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.record-item__meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: var(--ink-muted);
}

.record-item__link {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  color: var(--ink-muted);
  text-decoration: none;
  font-size: 12px;
}

.record-item__link:hover {
  color: var(--accent);
  text-decoration: underline;
}

/* ── Detail Overlay ──────────────────────────────────────────────── */
.detail-overlay {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  background: rgba(0, 0, 0, 0.20);
  backdrop-filter: blur(4px);
}

.detail-card {
  width: 100%;
  max-width: 720px;
  max-height: 70vh;
  margin-bottom: 40px;
  display: flex;
  flex-direction: column;
  border-radius: var(--radius);
  background: var(--surface);
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.15);
  overflow: hidden;
}

.detail-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px 12px;
  border-bottom: 1px solid var(--line);
}

.detail-card__head strong {
  font-size: 15px;
  font-weight: 600;
  display: block;
  margin-bottom: 6px;
}

.detail-card__actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.detail-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 12px;
  color: var(--ink-muted);
}

.detail-card__loading {
  display: flex;
  justify-content: center;
  padding: 32px;
}

.detail-card__body {
  padding: 16px 20px 20px;
  overflow-y: auto;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--ink);
}

/* ── Transitions ─────────────────────────────────────────────────── */
.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.2s ease;
}

.slide-up-enter-from,
.slide-up-leave-to {
  opacity: 0;
}

.slide-up-enter-from .detail-card,
.slide-up-leave-to .detail-card {
  transform: translateY(20px);
}

.spin {
  animation: spin 0.75s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
