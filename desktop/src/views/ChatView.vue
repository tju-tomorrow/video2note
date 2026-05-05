<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRoute } from "vue-router";
import { Bot, Database, FileText, Loader2, Send, User } from "lucide-vue-next";

const route = useRoute();

interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

const model = ref<"deepseek" | "mimo">("deepseek");
const useKB = ref(false);
const messages = ref<ChatMessage[]>([]);
const inputText = ref("");
const sending = ref(false);
const error = ref("");
const contextText = ref("");
const contextExpanded = ref(false);
const kbDocs = ref<Array<{ title: string; content: string; score: number }>>([]);

onMounted(() => {
  const text = (route.query.text as string) || "";
  if (text) {
    contextText.value = text;
    messages.value.push({
      role: "system",
      content: `以下是视频转写内容，请基于此内容回答用户问题：\n\n${text}`,
    });
  }
});

function autoResize(e: Event) {
  const el = e.target as HTMLTextAreaElement;
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 200) + "px";
}

async function send() {
  const text = inputText.value.trim();
  if (!text || sending.value) return;

  messages.value.push({ role: "user", content: text });
  inputText.value = "";
  sending.value = true;
  error.value = "";
  kbDocs.value = [];

  const bridge = window.desktopBridge;
  if (!bridge) {
    error.value = "请在桌面应用内运行";
    sending.value = false;
    return;
  }

  const msgs = messages.value.map((m: ChatMessage) => ({ role: m.role, content: m.content }));
  let chatMessages = msgs;
  if (useKB.value) {
    try {
      const kbRes = await bridge.kbSearch(text);
      if (kbRes.ok && kbRes.docs?.length) {
        kbDocs.value = kbRes.docs;
        const kbContext = kbRes.docs.map((d: any, i: number) => `[参考${i + 1}] ${d.title}\n${d.content}`).join("\n\n");
        chatMessages = [
          { role: "system", content: `以下是知识库中与用户问题相关的参考内容：\n\n${kbContext}\n\n请基于以上参考内容回答用户问题。` },
          ...msgs,
        ];
      }
    } catch {}
  }

  try {
    const resp = await bridge.chatSend(chatMessages, model.value);
    if (resp.ok || resp.text) {
      messages.value.push({ role: "assistant", content: resp.text || resp.reply });
    } else {
      error.value = resp.error || "请求失败";
    }
  } catch (e) {
    error.value = String(e);
  } finally {
    sending.value = false;
  }
}
</script>

<template>
  <div class="chat-page">
    <!-- 模型选择 -->
    <div class="chat-toolbar">
      <span class="chat-toolbar__label">模型:</span>
      <button
        class="model-btn"
        :class="{ 'model-btn--active': model === 'deepseek' }"
        @click="model = 'deepseek'"
      >DeepSeek V4 Pro Flash</button>
      <button
        class="model-btn"
        :class="{ 'model-btn--active': model === 'mimo' }"
        @click="model = 'mimo'"
      >MiMo V2.5 Pro</button>
      <span class="chat-toolbar__sep" />
      <button
        class="kb-btn"
        :class="{ 'kb-btn--active': useKB }"
        @click="useKB = !useKB"
        title="基于素材库知识库回答"
      >
        <Database :size="13" />
        知识库
      </button>
    </div>

    <!-- 转写内容上下文 -->
    <div v-if="contextText" class="context-banner">
      <div class="context-banner__head" @click="contextExpanded = !contextExpanded">
        <FileText :size="14" />
        <span>已加载转写内容 ({{ contextText.length }} 字)</span>
        <span class="context-banner__toggle">{{ contextExpanded ? '收起' : '展开' }}</span>
      </div>
      <div v-if="contextExpanded" class="context-banner__body">{{ contextText }}</div>
    </div>

    <!-- 消息列表 -->
    <div class="chat-messages" ref="msgContainer">
      <div v-if="!messages.length && !contextText" class="chat-empty">
        <Bot :size="36" stroke-width="1.5" />
        <p>从提取结果点击"与Agent聊聊"开始对话</p>
        <p class="chat-empty__hint">也可以直接输入问题自由聊天</p>
      </div>

      <div
        v-for="(m, i) in messages.filter((m) => m.role !== 'system')"
        :key="i"
        class="chat-msg"
        :class="{ 'chat-msg--user': m.role === 'user', 'chat-msg--bot': m.role === 'assistant' }"
      >
        <div class="chat-msg__avatar">
          <User v-if="m.role === 'user'" :size="16" />
          <Bot v-else :size="16" />
        </div>
        <div class="chat-msg__bubble">{{ m.content }}</div>
      </div>

      <div v-if="sending" class="chat-msg chat-msg--bot">
        <div class="chat-msg__avatar"><Bot :size="16" /></div>
        <div class="chat-msg__bubble chat-msg__bubble--loading">
          <Loader2 :size="16" class="spin" />
        </div>
      </div>

      <div v-if="error" class="chat-error">{{ error }}</div>

      <!-- 知识库检索结果 -->
      <div v-if="kbDocs.length" class="kb-results">
        <div class="kb-results__head">
          <Database :size="13" />
          知识库匹配 {{ kbDocs.length }} 条
        </div>
        <div v-for="d in kbDocs" :key="d.id" class="kb-result-item">
          <span class="kb-result-item__score">{{ (d.score * 100).toFixed(0) }}%</span>
          <span class="kb-result-item__title">{{ d.title || '(无标题)' }}</span>
        </div>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="chat-input-area">
      <div class="chat-input-wrapper">
        <textarea
          v-model="inputText"
          placeholder="输入问题，基于视频内容与 Agent 对话..."
          :disabled="sending"
          rows="1"
          @keydown.enter.exact.prevent="send"
          @input="autoResize"
        />
        <button
          class="send-btn"
          :class="{ 'send-btn--active': inputText.trim() && !sending }"
          :disabled="sending || !inputText.trim()"
          @click="send"
        >
          <Send :size="16" />
        </button>
      </div>
      <p class="chat-input-hint">Enter 发送，Shift+Enter 换行</p>
    </div>
  </div>
</template>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 120px);
}

/* ── Toolbar ─────────────────────────────────────────────────────── */
.chat-toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  margin-bottom: 8px;
  flex-shrink: 0;
}

.chat-toolbar__label {
  font-size: 12px;
  color: var(--ink-muted);
  margin-right: 4px;
}

.model-btn {
  height: 28px;
  padding: 0 12px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface);
  color: var(--ink-soft);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.12s;
}

.model-btn:hover {
  background: var(--surface-muted);
}

.model-btn--active {
  background: var(--accent-soft);
  border-color: var(--accent);
  color: var(--accent);
}

.chat-toolbar__sep {
  width: 1px;
  height: 20px;
  background: var(--line);
  margin: 0 4px;
}

.kb-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 28px;
  padding: 0 12px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface);
  color: var(--ink-soft);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.12s;
}

.kb-btn:hover { background: var(--surface-muted); }

.kb-btn--active {
  background: rgba(74, 158, 96, 0.08);
  border-color: var(--success);
  color: var(--success);
}

/* ── KB Results ────────────────────────────────────────────────── */
.kb-results {
  margin-top: 8px;
  padding: 10px 14px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: var(--surface-muted);
}

.kb-results__head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 600;
  color: var(--ink-muted);
  margin-bottom: 6px;
}

.kb-result-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 0;
  font-size: 12px;
}

.kb-result-item__score {
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 600;
  color: var(--success);
  width: 36px;
}

.kb-result-item__title {
  color: var(--ink-soft);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── Context Banner ─────────────────────────────────────────────── */
.context-banner {
  border: 1px solid var(--accent-soft);
  border-radius: var(--radius-sm);
  background: var(--accent-soft);
  overflow: hidden;
  margin-bottom: 12px;
  flex-shrink: 0;
}

.context-banner__head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  cursor: pointer;
  font-size: 13px;
  color: var(--accent);
  font-weight: 500;
  user-select: none;
}

.context-banner__toggle {
  margin-left: auto;
  font-size: 12px;
  opacity: 0.7;
}

.context-banner__body {
  padding: 0 14px 14px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--ink);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow-y: auto;
  border-top: 1px solid var(--accent-soft);
  padding-top: 12px;
  margin: 0 14px;
}

/* ── Messages ───────────────────────────────────────────────────── */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chat-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 80px 24px;
  color: var(--ink-muted);
  text-align: center;
}

.chat-empty p {
  margin: 0;
  font-size: 14px;
}

.chat-empty__hint {
  font-size: 12px;
  opacity: 0.6;
}

.chat-msg {
  display: flex;
  gap: 10px;
  max-width: 85%;
}

.chat-msg--user {
  align-self: flex-end;
  flex-direction: row-reverse;
}

.chat-msg--bot {
  align-self: flex-start;
}

.chat-msg__avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: var(--surface-muted);
  color: var(--ink-soft);
  border: 1px solid var(--line);
}

.chat-msg--user .chat-msg__avatar {
  background: var(--accent-soft);
  color: var(--accent);
  border-color: transparent;
}

.chat-msg__bubble {
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  background: var(--surface);
  border: 1px solid var(--line);
  font-size: 13px;
  line-height: 1.6;
  color: var(--ink);
  white-space: pre-wrap;
  word-break: break-word;
}

.chat-msg--user .chat-msg__bubble {
  background: var(--accent-soft);
  border-color: transparent;
}

.chat-msg__bubble--loading {
  padding: 8px 14px;
}

.chat-error {
  align-self: center;
  padding: 8px 14px;
  border-radius: 6px;
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 12px;
}

/* ── Input Area ─────────────────────────────────────────────────── */
.chat-input-area {
  flex-shrink: 0;
  padding: 16px 0 8px;
}

.chat-input-wrapper {
  display: flex;
  align-items: flex-end;
  gap: 0;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  padding: 8px 8px 8px 16px;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.chat-input-wrapper:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.chat-input-wrapper textarea {
  flex: 1;
  border: none;
  background: transparent;
  outline: none;
  resize: none;
  font-size: 14px;
  line-height: 1.5;
  color: var(--ink);
  max-height: 200px;
  padding: 4px 0;
  font-family: var(--font-ui);
}

.chat-input-wrapper textarea::placeholder {
  color: var(--ink-muted);
  opacity: 0.7;
}

.send-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border: none;
  border-radius: 8px;
  background: var(--surface-muted);
  color: var(--ink-muted);
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.15s, color 0.15s;
}

.send-btn--active {
  background: var(--accent);
  color: #fff;
}

.send-btn--active:hover {
  background: var(--accent-strong);
}

.send-btn:disabled {
  cursor: not-allowed;
}

.chat-input-hint {
  margin: 6px 0 0;
  font-size: 11px;
  color: var(--ink-muted);
  text-align: center;
  opacity: 0.6;
}

.spin { animation: spin 0.75s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
