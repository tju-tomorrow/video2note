<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import {
  AlertCircle,
  Archive,
  Bot,
  CheckCircle2,
  Clock3,
  Copy,
  Download,
  Eraser,
  FileVideo,
  Link2,
  Loader2,
  Play,
  Timer,
  Upload,
  WandSparkles,
  X,
} from "lucide-vue-next";
import { useTranscription } from "../composables/useTranscription";

const router = useRouter();

const {
  linkInput,
  status,
  resultText,
  videoUrl,
  running,
  copyFeedback,
  primaryUrl,
  inputMode,
  logLines,
  statusKind,
  statusLabel,
  pipelineSteps,
  totalTimeMs,
  localFileName,
  isFileMode,
  formatMs,
  onFileInputChange,
  copyResult,
  clearLink,
  clearFile,
  pickFile,
  onDragOver,
  onDragLeave,
  onDrop,
  run,
  saveToLibrary,
  saving,
  saved,
} = useTranscription();

const filePicker = ref<HTMLInputElement | null>(null);

function triggerFilePicker() {
  if (window.desktopBridge?.pickVideoFile) {
    pickFile();
  } else {
    filePicker.value?.click();
  }
}

onMounted(() => {
  if (filePicker.value) {
    filePicker.value.accept = ".mp4,.mov,.avi,.mkv,.flv,.webm,.m4v,.mp3,.wav,.m4a,.aac,.flac,.ogg";
  }
});

const VIDEO_STEPS = ["识别链接", "下载视频", "提取转写", "格式化"] as const;
const FILE_STEPS = ["提取音频", "加载模型", "转写", "格式化"] as const;
const WEB_STEPS = ["识别链接", "抓取网页", "格式化"] as const;
</script>

<template>
  <div
    class="extract-workspace"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
  >
    <!-- 隐藏的文件选择器 -->
    <input
      ref="filePicker"
      type="file"
      style="display:none"
      @change="onFileInputChange"
    />

    <!-- 左栏：输入区 -->
    <section class="extract-input" aria-labelledby="source-heading">
      <div class="section-head">
        <h2 id="source-heading">输入内容</h2>
        <span class="section-badge">链接</span>
      </div>

      <textarea
        id="link-field"
        v-model="linkInput"
        :placeholder="isFileMode ? '已选择本地文件...' : '粘贴抖音/B站分享链接或网页链接...'"
        :disabled="isFileMode"
        spellcheck="false"
      />

      <div class="input-meta" aria-live="polite">
        <!-- 本地文件标签 -->
        <div v-if="isFileMode" class="file-chip">
          <FileVideo :size="14" aria-hidden="true" />
          <span>{{ localFileName }}</span>
          <button class="file-chip__clear" @click="clearFile" title="取消选择">
            <X :size="13" aria-hidden="true" />
          </button>
        </div>
        <!-- URL 标签 -->
        <div v-else-if="primaryUrl" class="url-chip" :title="primaryUrl">
          <Link2 :size="13" aria-hidden="true" />
          <span>{{ primaryUrl }}</span>
        </div>
        <span v-else class="input-hint">支持抖音、B站链接和本地视频文件</span>
      </div>

      <div class="extract-actions">
        <button type="button" class="primary" :disabled="running" @click="run">
          <Loader2 v-if="running" class="spin" :size="16" aria-hidden="true" />
          <Play v-else :size="16" aria-hidden="true" />
          {{ running ? "处理中" : "开始提取" }}
        </button>
        <button
          type="button"
          class="ghost"
          :disabled="!linkInput.trim() && !isFileMode"
          @click="isFileMode ? clearFile() : clearLink()"
        >
          <Eraser :size="15" aria-hidden="true" />
          清空
        </button>
        <button type="button" class="ghost upload-btn" @click="triggerFilePicker" title="上传本地视频">
          <Upload :size="15" aria-hidden="true" />
          上传视频
        </button>
      </div>

      <!-- 运行中/未运行：静态占位 pipeline -->
      <div v-if="!pipelineSteps" class="pipeline">
        <div
          v-for="(step, index) in (isFileMode ? FILE_STEPS : inputMode === 'web' ? WEB_STEPS : VIDEO_STEPS)"
          :key="step"
          class="pipeline-step"
          :class="{ 'pipeline-step--active': running && index === 1 }"
        >
          <span>{{ index + 1 }}</span>
          <strong>{{ step }}</strong>
        </div>
      </div>

      <!-- 完成后：真实计时 pipeline -->
      <div v-else class="timing-panel">
        <div class="timing-panel__head">
          <Timer :size="13" aria-hidden="true" />
          <span>耗时分析</span>
          <strong>{{ formatMs(totalTimeMs) }}</strong>
        </div>
        <div class="timing-steps">
          <div
            v-for="(s, i) in pipelineSteps"
            :key="s.step"
            class="timing-step"
            :class="{ 'timing-step--error': s.status === 'error' }"
          >
            <div class="timing-step__head">
              <span class="timing-step__index">{{ i + 1 }}</span>
              <strong>{{ s.step }}</strong>
              <small v-if="s.meta" class="timing-step__meta">{{ s.meta }}</small>
              <span class="timing-step__time">{{ formatMs(s.displayMs) }}</span>
              <CheckCircle2
                v-if="s.status === 'done'"
                :size="13"
                class="timing-step__icon timing-step__icon--done"
              />
              <AlertCircle
                v-else
                :size="13"
                class="timing-step__icon timing-step__icon--err"
              />
            </div>
            <div class="timing-bar">
              <div
                class="timing-bar__fill"
                :style="{ width: Math.max(s.pct, 2) + '%' }"
              />
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 右栏：结果 + 日志 -->
    <section class="extract-output">
      <div class="section-head">
        <h2 id="result-heading">输出结果</h2>
        <div
          class="status-pill"
          :class="{
            success: statusKind === 'success',
            error: statusKind === 'error',
            running: statusKind === 'running',
          }"
        >
          <CheckCircle2 v-if="statusKind === 'success'" :size="12" aria-hidden="true" />
          <Clock3 v-else :size="12" aria-hidden="true" />
          <strong>{{ statusLabel }}</strong>
        </div>
      </div>

      <div v-if="videoUrl" class="video-box">
        <video :src="videoUrl" controls preload="metadata" class="video-player" />
      </div>

      <div class="result-shell">
        <p v-if="!resultText.trim()" class="result-empty">
          {{ status || '等待提取完成...' }}
        </p>
        <p v-else class="result-body">{{ resultText }}</p>
      </div>

      <div class="result-toolbar">
        <button type="button" class="ghost" :disabled="!resultText.trim()" @click="copyResult">
          <Copy :size="14" aria-hidden="true" />
          {{ copyFeedback || "复制" }}
        </button>
        <button type="button" class="ghost save-btn" :disabled="!resultText.trim() || saved" @click="saveToLibrary">
          <Archive :size="14" aria-hidden="true" />
          {{ saved ? '已保存' : saving ? '保存中...' : '保存到素材库' }}
        </button>
        <button
          type="button"
          class="ghost chat-btn"
          :disabled="!resultText.trim()"
          @click="router.push({ name: 'chat', query: { text: resultText } })"
        >
          <Bot :size="14" aria-hidden="true" />
          与Agent聊聊
        </button>
      </div>

      <!-- 日志 -->
      <div class="log-section">
        <div class="log-section__head">
          <h3>执行日志</h3>
        </div>
        <div class="log-box">
          <p v-if="!logLines.length" class="log-empty">暂无运行记录</p>
          <ul v-else class="log-timeline">
            <li v-for="(line, i) in logLines" :key="i">{{ line }}</li>
          </ul>
        </div>
      </div>
    </section>

    <!-- 拖拽遮罩 -->
    <Transition name="fade">
      <div v-if="isDragOver" class="drag-overlay">
        <Upload :size="36" aria-hidden="true" />
        <span>释放以上传视频文件</span>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
/* ── 文件选择标签 ────────────────────────────────────────────────── */
.file-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 5px 6px 5px 12px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 13px;
  font-weight: 500;
}

.file-chip span {
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-chip__clear {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--accent);
  cursor: pointer;
  flex-shrink: 0;
}

.file-chip__clear:hover {
  background: rgba(218, 119, 86, 0.15);
}

/* ── 上传按钮 ───────────────────────────────────────────────────── */
.upload-btn {
  margin-left: auto;
}

/* ── 拖拽遮罩 ───────────────────────────────────────────────────── */
.drag-overlay {
  position: absolute;
  inset: 0;
  z-index: 30;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: rgba(250, 250, 250, 0.92);
  border: 2px dashed var(--accent);
  border-radius: var(--radius);
  color: var(--accent);
  font-size: 15px;
  font-weight: 500;
  pointer-events: none;
}

[data-theme="dark"] .drag-overlay {
  background: rgba(26, 26, 26, 0.92);
  border-color: var(--accent);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.extract-workspace {
  display: grid;
  grid-template-columns: minmax(400px, 1fr) minmax(450px, 1fr);
  gap: 0;
  height: calc(100vh - 120px);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  overflow: hidden;
  position: relative;
}

/* ── 左栏：输入 ──────────────────────────────────────────────────── */
.extract-input {
  padding: 24px 28px;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--line);
}

/* ── 右栏：输出 + 日志 ──────────────────────────────────────────── */
.extract-output {
  display: flex;
  flex-direction: column;
  background: var(--surface-muted);
}

.extract-output .section-head {
  padding: 24px 28px 0;
}

.extract-output .video-box {
  margin: 16px 28px 0;
}

.extract-output .result-shell {
  margin: 16px 28px 0;
  flex: 1;
  min-height: 250px;
  overflow: auto;
}

.extract-output .result-toolbar {
  padding: 0 28px;
  margin-top: 10px;
  margin-bottom: 16px;
}

/* ── Section Head ────────────────────────────────────────────────── */
.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.section-head h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--ink);
}

.section-badge {
  display: inline-flex;
  align-items: center;
  height: 24px;
  padding: 0 10px;
  border-radius: 6px;
  background: var(--surface-muted);
  color: var(--ink-soft);
  font-size: 12px;
  font-weight: 500;
}

/* ── Textarea ────────────────────────────────────────────────────── */
.extract-input textarea {
  width: 100%;
  flex: 1;
  min-height: 200px;
  resize: none;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  color: var(--ink);
  background: var(--surface-muted);
  line-height: 1.65;
  outline: none;
  caret-color: var(--accent);
  font-size: 14px;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.extract-input textarea:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.extract-input textarea::placeholder {
  color: var(--ink-muted);
}

.extract-input textarea:disabled {
  opacity: 0.6;
}

/* ── Input Meta ──────────────────────────────────────────────────── */
.input-meta {
  display: flex;
  align-items: center;
  min-height: 28px;
  margin-top: 10px;
  color: var(--ink-muted);
  font-size: 12px;
}

.input-hint {
  font-size: 12px;
  color: var(--ink-muted);
}

.url-chip {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  color: var(--accent);
  background: var(--accent-soft);
  font-size: 12px;
  font-weight: 500;
}

.url-chip span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Extract Actions ─────────────────────────────────────────────── */
.extract-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 16px;
}

/* ── Pipeline ────────────────────────────────────────────────────── */
.extract-input .pipeline {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
  margin-top: 20px;
}

.extract-input .pipeline-step {
  min-height: 60px;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: var(--surface-muted);
}

.extract-input .pipeline-step span {
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  margin-bottom: 6px;
  border-radius: 50%;
  color: var(--ink-muted);
  background: var(--line);
  font-size: 10px;
  font-weight: 700;
  font-family: var(--font-mono);
}

.extract-input .pipeline-step strong {
  display: block;
  color: var(--ink-soft);
  font-size: 12px;
  font-weight: 500;
}

.extract-input .pipeline-step--active {
  border-color: var(--blue);
  background: rgba(91, 139, 212, 0.04);
}

.extract-input .pipeline-step--active span {
  color: var(--blue);
  background: rgba(91, 139, 212, 0.10);
}

/* ── Timing Panel ────────────────────────────────────────────────── */
.extract-input .timing-panel {
  margin-top: 20px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.extract-input .timing-panel__head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--line);
  color: var(--ink-soft);
  font-size: 12px;
  font-weight: 500;
}

.extract-input .timing-panel__head strong {
  margin-left: auto;
  color: var(--accent);
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
}

.extract-input .timing-steps {
  display: flex;
  flex-direction: column;
}

.extract-input .timing-step {
  padding: 10px 12px;
  border-bottom: 1px solid var(--line);
}

.extract-input .timing-step:last-child {
  border-bottom: 0;
}

.extract-input .timing-step__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.extract-input .timing-step__index {
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  color: var(--ink-muted);
  background: var(--line);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  flex-shrink: 0;
}

.extract-input .timing-step--error .timing-step__index {
  color: var(--danger);
  background: var(--danger-soft);
}

.extract-input .timing-step strong {
  color: var(--ink-soft);
  font-size: 12px;
  font-weight: 500;
}

.extract-input .timing-step__meta {
  color: var(--ink-muted);
  font-family: var(--font-mono);
  font-size: 10px;
}

.extract-input .timing-step__time {
  margin-left: auto;
  color: var(--ink-muted);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 500;
}

.extract-input .timing-step__icon {
  flex-shrink: 0;
}

.extract-input .timing-step__icon--done { color: var(--success); }
.extract-input .timing-step__icon--err { color: var(--danger); }

.extract-input .timing-bar {
  height: 3px;
  border-radius: 999px;
  background: var(--line);
  overflow: hidden;
}

.extract-input .timing-bar__fill {
  height: 100%;
  border-radius: 999px;
  background: var(--accent);
  transition: width 0.6s cubic-bezier(0.22, 0.61, 0.36, 1);
  min-width: 4px;
}

.extract-input .timing-step--error .timing-bar__fill {
  background: var(--danger);
}

/* ── Result Shell ────────────────────────────────────────────────── */
.extract-output .result-shell {
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: var(--surface);
}

.result-empty {
  margin: 0;
  font-size: 13px;
  color: var(--ink-muted);
}

.result-body {
  margin: 0;
  font-size: 14px;
  line-height: 1.7;
  color: var(--ink);
  white-space: pre-wrap;
  word-break: break-word;
}

.result-toolbar {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
}

/* ── Video ───────────────────────────────────────────────────────── */
.video-box {
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.video-player {
  display: block;
  width: 100%;
  max-height: 360px;
  background: #000;
}

/* ── Log ─────────────────────────────────────────────────────────── */
.log-section {
  border-top: 1px solid var(--line);
  margin-top: 8px;
  padding: 16px 28px 20px;
}

.log-section__head h3 {
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
}

.log-box {
  min-height: 60px;
  max-height: 130px;
  overflow: auto;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: var(--surface);
}

.log-empty {
  margin: 0;
  font-size: 12px;
  color: var(--ink-muted);
}

.log-timeline {
  list-style: none;
  margin: 0;
  padding: 0;
}

.log-timeline li {
  padding: 0 0 6px 16px;
  position: relative;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-soft);
  line-height: 1.5;
}

.log-timeline li::before {
  content: "";
  position: absolute;
  left: 2px;
  top: 5px;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--accent);
  opacity: 0.5;
}

.log-timeline li:last-child {
  padding-bottom: 0;
}

/* ── Status Pill ─────────────────────────────────────────────────── */
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 24px;
  padding: 0 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--ink-muted);
  font-size: 12px;
  font-weight: 500;
}

.status-pill.success {
  color: var(--success);
  border-color: rgba(74, 158, 96, 0.18);
  background: var(--success-soft);
}

.status-pill.error {
  color: var(--danger);
  border-color: rgba(212, 85, 85, 0.18);
  background: var(--danger-soft);
}

.status-pill.running {
  color: var(--blue);
  border-color: rgba(91, 139, 212, 0.18);
  background: rgba(91, 139, 212, 0.05);
}

/* ── Shared ──────────────────────────────────────────────────────── */
.spin {
  animation: spin 0.75s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ── Responsive ──────────────────────────────────────────────────── */
@media (max-width: 900px) {
  .extract-workspace {
    grid-template-columns: 1fr;
  }

  .extract-input {
    border-right: 0;
    border-bottom: 1px solid var(--line);
  }
}
</style>
