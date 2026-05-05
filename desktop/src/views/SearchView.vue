<script setup lang="ts">
import { computed, ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { Bot, Globe, Link2, Loader2, Play, X } from "lucide-vue-next";

const router = useRouter();

const MAX_SELECT = 3;

const PLATFORMS = [
  { key: "douyin", label: "抖音", url: "https://www.douyin.com" },
  { key: "bilibili", label: "B站", url: "https://www.bilibili.com" },
] as const;

const activePlatform = ref("douyin");
const webviewRef = ref<HTMLElement | null>(null);
const detectedLinks = ref<SearchResult[]>([]);
const selected = ref<SearchResult[]>([]);
const extractingUrls = ref<Set<string>>(new Set());
const extractResults = ref<Map<string, string>>(new Map());
const webviewLoading = ref(false);
const interceptedLink = ref<{ url: string; title: string } | null>(null);

const currentUrl = computed(() => PLATFORMS.find((p) => p.key === activePlatform.value)?.url || "");

const VIDEO_URL_RE = /(?:douyin\.com\/(?:video\/\d+|user\/.*modal_id=)|v\.douyin\.com\/[A-Za-z0-9]+|bilibili\.com\/video\/[A-Za-z0-9]+|b23\.tv\/[A-Za-z0-9]+|bilibili\.com\/bangumi\/play\/[A-Za-z0-9]+)/;

function isVideoUrl(url: string): boolean {
  return VIDEO_URL_RE.test(url);
}

function switchPlatform(key: string) {
  activePlatform.value = key;
  detectedLinks.value = [];
  selected.value = [];
  extractResults.value.clear();
  interceptedLink.value = null;
  const wv = webviewRef.value as any;
  if (wv) {
    const plat = PLATFORMS.find((p) => p.key === key);
    if (plat) wv.loadURL(plat.url);
  }
}

function addLinkFromIntercept(url: string, title: string) {
  const exists = detectedLinks.value.some((l) => l.url === url);
  if (exists) return;
  const domain = url.includes("bilibili") || url.includes("b23.tv") ? "bilibili" : "douyin";
  detectedLinks.value.push({
    url,
    title: title || url,
    platform: domain,
    snippet: "",
  });
  interceptedLink.value = { url, title: title || url };
  // 自动加入选中列表（未满时）
  if (selected.value.length < MAX_SELECT && !selected.value.some((s) => s.url === url)) {
    selected.value.push({ url, title: title || url, platform: domain, snippet: "" });
  }
}

/** 注入点击拦截脚本：点击视频链接时不跳转，而是捕获链接用于转写 */
function injectClickInterceptor() {
  const wv = webviewRef.value as any;
  if (!wv) return;

  const platformKey = activePlatform.value;
  const patternRe = platformKey === "douyin"
    ? /douyin\.com\/video\/\d+|douyin\.com\/user\/.*modal_id=|v\.douyin\.com\/[A-Za-z0-9]+/
    : /bilibili\.com\/video\/[A-Za-z0-9]+|b23\.tv\/[A-Za-z0-9]+|bilibili\.com\/bangumi\/play\/[A-Za-z0-9]+/;

  const patternSource = JSON.stringify(patternRe.source);

  wv.executeJavaScript(
    `(function(p){` +
    `document.addEventListener("click",function(e){` +
    `var a=e.target.closest("a[href]");` +
    `if(!a||!a.href)return;` +
    `if(!(new RegExp(p)).test(a.href))return;` +
    `e.preventDefault();` +
    `e.stopPropagation();` +
    `var t=(a.textContent||"").trim().slice(0,120)||a.href.split("/").pop()||a.href.slice(0,60);` +
    `console.log("__VD_LINK__"+JSON.stringify({url:a.href,title:t}));` +
    `},true);` +
    `})(` + patternSource + `)`
  );
}

function mergeLinks(newLinks: Array<{ url: string; title: string }>) {
  for (const link of newLinks) {
    const exists = detectedLinks.value.some((l) => l.url === link.url);
    if (!exists) {
      const domain = link.url.includes("bilibili") || link.url.includes("b23.tv") ? "bilibili" : "douyin";
      detectedLinks.value.push({
        url: link.url,
        title: link.title || link.url,
        platform: domain,
        snippet: "",
      });
    }
  }
}

function setupWebview() {
  const wv = webviewRef.value as any;
  if (!wv) return;

  wv.addEventListener("did-finish-load", () => {
    webviewLoading.value = false;
    injectClickInterceptor();
  });

  wv.addEventListener("did-start-loading", () => {
    webviewLoading.value = true;
  });

  wv.addEventListener("did-navigate", () => {
    injectClickInterceptor();
  });

  wv.addEventListener("console-message", (e: any) => {
    if (e.message.startsWith("__VD_LINK__")) {
      try {
        const data = JSON.parse(e.message.slice(11));
        if (data.url && isVideoUrl(data.url)) {
          addLinkFromIntercept(data.url, data.title || data.url);
        }
      } catch {}
    }
  });

  wv.addEventListener("did-fail-load", (e: any) => {
    webviewLoading.value = false;
    console.error("webview load failed:", e.errorDescription);
  });
}

function toggleSelect(r: SearchResult) {
  const idx = selected.value.findIndex((s) => s.url === r.url);
  if (idx >= 0) {
    selected.value.splice(idx, 1);
  } else if (selected.value.length < MAX_SELECT) {
    selected.value.push({ ...r });
  }
}

function isSelected(url: string) {
  return selected.value.some((s) => s.url === url);
}

function removeSelected(url: string) {
  selected.value = selected.value.filter((s) => s.url !== url);
  extractResults.value.delete(url);
}

async function extractOne(r: SearchResult) {
  const bridge = window.desktopBridge;
  if (!bridge) return;

  extractingUrls.value.add(r.url);
  try {
    const resp = await bridge.transcribeLink(r.url);
    extractResults.value.set(r.url, resp.text || "提取失败：无结果");
  } catch (e) {
    extractResults.value.set(r.url, `提取失败：${e}`);
  } finally {
    extractingUrls.value.delete(r.url);
  }
}

function platformLabel(p: string) {
  if (p === "douyin") return "抖音";
  if (p === "bilibili") return "B站";
  return p;
}

async function saveToLibrary(r: SearchResult) {
  const bridge = window.desktopBridge;
  if (!bridge) return;
  try {
    await bridge.saveRecord({
      url: r.url,
      platform: r.platform,
      sourceType: "video",
      formattedText: extractResults.value.get(r.url) || "",
    });
  } catch {}
}

onMounted(() => {
  setupWebview();
});
</script>

<template>
  <div class="search-webview-page">
    <!-- 平台切换 tab -->
    <div class="platform-tabs">
      <button
        v-for="p in PLATFORMS"
        :key="p.key"
        class="plat-tab"
        :class="{ 'plat-tab--active': activePlatform === p.key }"
        @click="switchPlatform(p.key)"
      >
        <Globe :size="14" />
        {{ p.label }}
      </button>
      <span class="platform-hint">点击视频卡片即可捕获链接</span>
    </div>

    <!-- webview -->
    <webview
      ref="webviewRef"
      :src="currentUrl"
      class="search-webview"
    />

    <div v-if="webviewLoading" class="webview-loading-bar" />

    <!-- 刚捕获的链接提示 -->
    <div v-if="interceptedLink" class="capture-toast">
      <Link2 :size="14" />
      <span class="capture-toast__label">已捕获：</span>
      <strong>{{ interceptedLink.title }}</strong>
    </div>

    <!-- 底部卡片区 -->
    <div class="bottom-cards" v-if="detectedLinks.length || selected.length">
      <div v-if="selected.length" class="selected-row">
        <div v-for="r in selected" :key="'s-' + r.url" class="mini-card">
          <div class="mini-card__info">
            <span class="mini-card__plat">{{ platformLabel(r.platform) }}</span>
            <strong>{{ r.title }}</strong>
          </div>
          <div class="mini-card__actions">
            <button class="primary" :disabled="extractingUrls.has(r.url)" @click="extractOne(r)">
              <Loader2 v-if="extractingUrls.has(r.url)" class="spin" :size="12" />
              <Play v-else :size="12" />
              {{ extractingUrls.has(r.url) ? '提取中' : '提取' }}
            </button>
            <button class="ghost" @click="removeSelected(r.url)">
              <X :size="13" />
            </button>
          </div>
          <div v-if="extractResults.has(r.url)" class="mini-card__result">
            <div class="mini-card__result-text">{{ extractResults.get(r.url) }}</div>
            <div class="mini-card__result-actions">
              <button class="ghost" @click="saveToLibrary(r)">保存到素材库</button>
              <button
                class="ghost chat-btn"
                @click="router.push({ name: 'chat', query: { text: extractResults.get(r.url) || '' } })"
              >
                <Bot :size="13" />
                与Agent聊聊
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.search-webview-page {
  height: calc(100vh - 120px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ── 平台 tab ───────────────────────────────────────────────────── */
.platform-tabs {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  flex-shrink: 0;
}

.platform-hint {
  margin-left: auto;
  font-size: 11px;
  color: var(--ink-muted);
  opacity: 0.7;
}

.plat-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 14px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--ink-soft);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.12s, border-color 0.12s, color 0.12s;
}

.plat-tab:hover {
  background: var(--surface-muted);
  color: var(--ink);
}

.plat-tab--active {
  background: var(--accent-soft);
  border-color: var(--accent);
  color: var(--accent);
}

/* ── webview ────────────────────────────────────────────────────── */
.search-webview {
  flex: 1;
  width: 100%;
  border: 1px solid var(--line);
  border-radius: var(--radius);
}

.webview-loading-bar {
  height: 3px;
  background: var(--accent);
  animation: loadingPulse 1.5s ease-in-out infinite;
  flex-shrink: 0;
}

@keyframes loadingPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* ── 捕获提示 ────────────────────────────────────────────────────── */
.capture-toast {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  margin: 8px 0;
  border: 1px solid var(--accent);
  border-radius: var(--radius-sm);
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 13px;
  flex-shrink: 0;
}

.capture-toast__label {
  font-weight: 500;
}

.capture-toast strong {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
}

/* ── 底部 ───────────────────────────────────────────────────────── */
.bottom-cards {
  border-top: 1px solid var(--line);
  background: var(--surface);
  max-height: 40vh;
  overflow-y: auto;
  flex-shrink: 0;
}

.selected-row {
  display: flex;
  gap: 10px;
  padding: 12px 16px;
  overflow-x: auto;
  border-bottom: 1px solid var(--line);
}

.mini-card {
  flex: 0 0 320px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: var(--surface);
  overflow: hidden;
}

.mini-card__info {
  padding: 12px 14px 8px;
}

.mini-card__plat {
  display: inline-block;
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 3px;
  background: var(--surface-muted);
  color: var(--ink-muted);
  margin-bottom: 6px;
}

.mini-card__info strong {
  display: block;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.mini-card__actions {
  display: flex;
  gap: 6px;
  padding: 0 14px 12px;
}

.mini-card__actions .primary {
  height: 30px;
  min-width: 80px;
  font-size: 12px;
  padding: 0 14px;
}

.mini-card__actions .ghost {
  height: 30px;
  min-width: 30px;
  padding: 0;
}

.mini-card__result {
  padding: 10px 14px;
  border-top: 1px solid var(--line);
  background: var(--surface-muted);
  font-size: 12px;
  line-height: 1.6;
  max-height: 160px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--ink);
}

/* ── Shared ─────────────────────────────────────────────────────── */
.spin {
  animation: spin 0.75s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
