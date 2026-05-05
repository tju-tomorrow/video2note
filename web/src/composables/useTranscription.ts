import { computed, ref, watch } from "vue";
import { api } from "../api";

const VIDEO_URL_RE =
  /https?:\/\/(?:(?:v\.douyin\.com|www\.douyin\.com|www\.iesdouyin\.com|iesdouyin\.com|douyin\.com|www\.bilibili\.com|bilibili\.com|m\.bilibili\.com|b23\.tv)\/)[^\s]*/gi;
const ANY_URL_RE = /https?:\/\/[^\s]+/g;

const VIDEO_EXTENSIONS = [".mp4", ".mov", ".avi", ".mkv", ".flv", ".webm", ".m4v"];
const AUDIO_EXTENSIONS = [".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"];

export type InputMode = "video" | "web" | "file" | "unknown";

export interface StepTiming {
  step: string;
  durationMs: number;
  status: "done" | "error" | "running";
  meta?: string;
}

export function useTranscription() {
  const linkInput = ref("");
  const status = ref("");
  const logsText = ref("");
  const resultText = ref("");
  const videoUrl = ref("");
  const running = ref(false);
  const copyFeedback = ref("");
  const stepTimings = ref<StepTiming[]>([]);
  const localFilePath = ref("");
  const localFileName = ref("");
  const isDragOver = ref(false);
  const saving = ref(false);
  const saved = ref(false);
  const saveContext = ref<Record<string, unknown>>({});

  const detectedUrls = computed(() => {
    const text = linkInput.value;
    const found = text.match(ANY_URL_RE);
    if (!found?.length) return [];
    return [...new Set(found)];
  });

  const primaryUrl = computed(() => detectedUrls.value[0] ?? "");

  const isFileMode = computed(() => !!localFilePath.value);

  const inputMode = computed<InputMode>(() => {
    if (localFilePath.value) return "file";
    const url = primaryUrl.value;
    if (!url) return "unknown";
    const videoMatch = url.match(VIDEO_URL_RE);
    if (videoMatch?.length) return "video";
    return "web";
  });

  const logLines = computed(() =>
    logsText.value
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean),
  );

  const statusKind = computed(() => {
    const s = status.value;
    if (s.includes("失败") || s.includes("未检测到")) return "error";
    if (s.includes("完成")) return "success";
    if (s.includes("执行中")) return "running";
    return "idle";
  });

  const statusLabel = computed(() => {
    if (statusKind.value === "running") return "进行中";
    if (statusKind.value === "success") return "已完成";
    if (statusKind.value === "error") return "出错";
    return "就绪";
  });

  const pipelineSteps = computed(() => {
    if (stepTimings.value.length === 0) return null;
    const steps = stepTimings.value.filter((t) => t.step !== "总计");
    const total = stepTimings.value.find((t) => t.step === "总计");
    const totalMs = total ? total.durationMs : 1;
    return steps.map((s) => ({
      ...s,
      pct: totalMs > 0 ? Math.round((s.durationMs / totalMs) * 100) : 0,
      displayMs: s.durationMs,
    }));
  });

  const totalTimeMs = computed(() => {
    const total = stepTimings.value.find((t) => t.step === "总计");
    return total ? total.durationMs : 0;
  });

  function formatMs(ms: number): string {
    if (ms < 0) return "--";
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
    const minutes = Math.floor(ms / 60_000);
    const seconds = Math.round((ms % 60_000) / 1000);
    return `${minutes}m ${seconds}s`;
  }

  function formatFileSize(bytes: number): string {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  watch(linkInput, () => {
    copyFeedback.value = "";
  });

  function isValidVideoFile(filename: string): boolean {
    const ext = filename.substring(filename.lastIndexOf(".")).toLowerCase();
    return VIDEO_EXTENSIONS.includes(ext) || AUDIO_EXTENSIONS.includes(ext);
  }

  async function copyResult() {
    const text = resultText.value.trim();
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      copyFeedback.value = "已复制";
      window.setTimeout(() => {
        copyFeedback.value = "";
      }, 2000);
    } catch {
      copyFeedback.value = "复制失败";
    }
  }

  async function saveToLibrary() {
    if (saved.value || saving.value) return;
    saving.value = true;
    try {
      const data = { ...saveContext.value, formattedText: resultText.value };
      const resp = await api.save(data);
      if (resp.ok) saved.value = true;
    } catch {} finally {
      saving.value = false;
    }
  }

  function clearAll() {
    linkInput.value = "";
    localFilePath.value = "";
    localFileName.value = "";
    status.value = "";
    logsText.value = "";
    resultText.value = "";
    videoUrl.value = "";
    copyFeedback.value = "";
    stepTimings.value = [];
  }

  function clearLink() {
    linkInput.value = "";
    status.value = "";
    logsText.value = "";
    resultText.value = "";
    videoUrl.value = "";
    copyFeedback.value = "";
    stepTimings.value = [];
  }

  function clearFile() {
    localFilePath.value = "";
    localFileName.value = "";
    status.value = "";
    logsText.value = "";
    resultText.value = "";
    videoUrl.value = "";
    copyFeedback.value = "";
    stepTimings.value = [];
  }

  const fileInputRef = ref<HTMLInputElement | null>(null);

  function registerFileInput(el: HTMLInputElement | null) {
    fileInputRef.value = el;
  }

  function onFileInputChange(e: Event) {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    if (!isValidVideoFile(file.name)) {
      status.value = "失败：仅支持视频和音频文件。";
      return;
    }
    localFilePath.value = (file as any).path || file.name;
    localFileName.value = file.name;
    linkInput.value = "";
    input.value = "";
  }

  async function pickFile() {
    const bridge = window.desktopBridge;
    if (bridge) {
      const path = await bridge.pickVideoFile();
      if (path) {
        localFilePath.value = path;
        localFileName.value = path.split(/[/\\]/).pop() || path;
        linkInput.value = "";
      }
      return;
    }
    // 浏览器 fallback：使用隐藏的 <input type="file">
    const input = fileInputRef.value;
    if (input) {
      input.accept = ".mp4,.mov,.avi,.mkv,.flv,.webm,.m4v,.mp3,.wav,.m4a,.aac,.flac,.ogg";
      input.click();
    }
  }

  function onDragOver(e: DragEvent) {
    e.preventDefault();
    if (e.dataTransfer) {
      e.dataTransfer.dropEffect = "copy";
    }
    isDragOver.value = true;
  }

  function onDragLeave() {
    isDragOver.value = false;
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    isDragOver.value = false;
    const files = e.dataTransfer?.files;
    if (!files?.length) return;
    const file = files[0];
    if (!isValidVideoFile(file.name)) {
      status.value = "失败：仅支持视频和音频文件。";
      return;
    }
    localFilePath.value = (file as any).path || file.name;
    localFileName.value = file.name;
    linkInput.value = "";
  }

  async function runLink() {
    const raw = linkInput.value.trim();
    if (!raw) {
      status.value = "请先输入链接。";
      return;
    }
    running.value = true;
    status.value = "执行中...";
    logsText.value = "";
    resultText.value = "";
    videoUrl.value = "";
    stepTimings.value = [];

    try {
      const response = await api.extract(raw);
      if (!response.ok) throw new Error(response.error);
      logsText.value = (response.logs || []).join("\n");
      resultText.value = response.text;
      videoUrl.value = response.videoUrl ?? "";
      stepTimings.value = (response.timings ?? []) as StepTiming[];
      saveContext.value = response.saveContext || { url: primaryUrl.value };
      saved.value = false;
      status.value = "完成。";
    } catch (error) {
      status.value = "失败。";
      logsText.value = String(error);
    } finally {
      running.value = false;
    }
  }

  async function runFile() {
    const path = localFilePath.value;
    if (!path) {
      status.value = "请先选择文件。";
      return;
    }
    const bridge = window.desktopBridge;
    if (!bridge) {
      status.value = "失败。";
      logsText.value = "未检测到 Electron 预加载桥（请在桌面应用内运行）。";
      return;
    }

    running.value = true;
    status.value = "执行中...";
    logsText.value = "";
    resultText.value = "";
    videoUrl.value = "";
    stepTimings.value = [];

    try {
      const response = await api.extractFile(path);
      if (!response.ok) throw new Error(response.error);
      logsText.value = (response.logs || []).join("\n");
      resultText.value = response.text;
      videoUrl.value = response.videoUrl ?? "";
      stepTimings.value = (response.timings ?? []) as StepTiming[];
      saveContext.value = response.saveContext || { url: localFileName.value };
      saved.value = false;
      status.value = "完成。";
    } catch (error) {
      status.value = "失败。";
      logsText.value = String(error);
    } finally {
      running.value = false;
    }
  }

  async function run() {
    return runLink();
  }

  return {
    linkInput,
    status,
    logsText,
    resultText,
    videoUrl,
    running,
    copyFeedback,
    detectedUrls,
    primaryUrl,
    inputMode,
    logLines,
    statusKind,
    statusLabel,
    pipelineSteps,
    totalTimeMs,
    localFilePath,
    localFileName,
    isDragOver,
    isFileMode,
    formatMs,
    formatFileSize,
    isValidVideoFile,
    copyResult,
    clearAll,
    clearLink,
    clearFile,
    fileInputRef,
    registerFileInput,
    onFileInputChange,
    pickFile,
    onDragOver,
    onDragLeave,
    onDrop,
    run,
    saveToLibrary,
    saving,
    saved,
  };
}
