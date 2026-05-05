const { app, BrowserWindow, dialog, ipcMain, protocol } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const DEV_URL = "http://127.0.0.1:5173";

function findProjectRoot() {
  let current = process.cwd();
  for (;;) {
    const pyproject = path.join(current, "pyproject.toml");
    const moduleDir = path.join(current, "src", "video_extract2note");
    if (fs.existsSync(pyproject) && fs.existsSync(moduleDir)) {
      return current;
    }
    const parent = path.dirname(current);
    if (parent === current) {
      break;
    }
    current = parent;
  }
  throw new Error("未找到项目根目录（缺少 pyproject.toml）");
}

function resolvePython(projectRoot) {
  const explicit = process.env.VIDEO_EXTRACT2NOTE_PYTHON;
  if (explicit && explicit.trim()) {
    return explicit.trim();
  }
  if (process.platform === "win32") {
    const winVenv = path.join(projectRoot, ".venv", "Scripts", "python.exe");
    if (fs.existsSync(winVenv)) {
      return winVenv;
    }
    return "python";
  }
  const venvPython = path.join(projectRoot, ".venv", "bin", "python");
  if (fs.existsSync(venvPython)) {
    return venvPython;
  }
  return "python3";
}

/** 异步 spawn，避免阻塞 Electron 主进程导致窗口前台卡死（spawnSync 会占满主线程）。 */
function spawnPythonAsync(command, args, options) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      ...options,
      stdio: ["ignore", "pipe", "pipe"],
    });

    const stdoutChunks = [];
    const stderrChunks = [];
    let settled = false;

    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => stdoutChunks.push(chunk));
    child.stderr.on("data", (chunk) => stderrChunks.push(chunk));

    child.on("error", (err) => {
      if (settled) {
        return;
      }
      settled = true;
      reject(new Error(`启动 Python 失败: ${err.message}`));
    });

    child.on("close", (code) => {
      if (settled) {
        return;
      }
      settled = true;
      resolve({
        status: code,
        stdout: stdoutChunks.join(""),
        stderr: stderrChunks.join(""),
      });
    });
  });
}

function interpretBridgeOutput(result) {
  const stdout = (result.stdout || "").trim();
  let payload = null;
  if (stdout) {
    try {
      payload = JSON.parse(stdout);
    } catch {
      // 非 JSON：下面结合 exit code 处理
    }
  }

  if (payload && typeof payload === "object" && "ok" in payload) {
    if (payload.ok) {
      // list / search / get 返回 records 或 record
      if ("records" in payload || "record" in payload) return payload;
      if ("docs" in payload || "count" in payload) return payload;
      if ("reply" in payload) return { text: payload.reply, ok: true };
      // run_link 返回 text
      const videoUrl = payload.videoPath
        ? `local-file://${encodeURI(payload.videoPath)}`
        : null;
      return {
        text: payload.text ?? "",
        logs: Array.isArray(payload.logs) ? payload.logs : [],
        videoUrl,
        timings: Array.isArray(payload.timings) ? payload.timings : [],
        saveContext: payload.saveContext || {},
      };
    }
    throw new Error(payload.error || "未知错误");
  }

  if (result.status !== 0) {
    const errText = (result.stderr || "").trim();
    if (errText) {
      throw new Error(errText);
    }
    if (stdout && !payload) {
      throw new Error(`桥接输出解析失败: ${stdout.slice(0, 500)}`);
    }
    throw new Error("Python 执行失败。");
  }

  throw new Error(stdout ? `桥接输出解析失败: ${stdout.slice(0, 500)}` : "桥接无输出。");
}

async function transcribeLink(link) {
  const trimmed = String(link).trim();
  if (!trimmed) {
    throw new Error("链接不能为空。");
  }

  const projectRoot = findProjectRoot();
  const pythonBin = resolvePython(projectRoot);
  const result = await spawnPythonAsync(
    pythonBin,
    ["-m", "video_extract2note.desktop_bridge", "run", trimmed],
    { cwd: projectRoot }
  );

  return interpretBridgeOutput(result);
}

async function transcribeFile(filePath) {
  const trimmed = String(filePath).trim();
  if (!trimmed) {
    throw new Error("文件路径不能为空。");
  }

  const projectRoot = findProjectRoot();
  const pythonBin = resolvePython(projectRoot);
  const result = await spawnPythonAsync(
    pythonBin,
    ["-m", "video_extract2note.desktop_bridge", "file", trimmed],
    { cwd: projectRoot }
  );

  return interpretBridgeOutput(result);
}

async function pickVideoFile() {
  const { canceled, filePaths } = await dialog.showOpenDialog({
    title: "选择视频文件",
    filters: [
      { name: "视频文件", extensions: ["mp4", "mov", "avi", "mkv", "flv", "webm", "m4v"] },
      { name: "音频文件", extensions: ["mp3", "wav", "m4a", "aac", "flac", "ogg"] },
      { name: "所有文件", extensions: ["*"] },
    ],
    properties: ["openFile"],
  });
  if (canceled || !filePaths.length) {
    return null;
  }
  return filePaths[0];
}

async function searchVideos(query, limit = 15) {
  const trimmed = String(query).trim();
  if (!trimmed) {
    throw new Error("搜索关键词不能为空。");
  }
  const projectRoot = findProjectRoot();
  const pythonBin = resolvePython(projectRoot);
  const result = await spawnPythonAsync(
    pythonBin,
    ["-m", "video_extract2note.desktop_bridge", "search", trimmed, String(limit)],
    { cwd: projectRoot }
  );
  return interpretBridgeOutput(result);
}

async function saveRecord(data) {
  const projectRoot = findProjectRoot();
  const pythonBin = resolvePython(projectRoot);
  const result = await spawnPythonAsync(
    pythonBin,
    ["-m", "video_extract2note.desktop_bridge", "save", JSON.stringify(data)],
    { cwd: projectRoot }
  );
  return interpretBridgeOutput(result);
}

async function chatSend(messages, model) {
  const projectRoot = findProjectRoot();
  const pythonBin = resolvePython(projectRoot);
  const result = await spawnPythonAsync(
    pythonBin,
    ["-m", "video_extract2note.desktop_bridge", "chat", JSON.stringify({ messages, model })],
    { cwd: projectRoot }
  );
  return interpretBridgeOutput(result);
}

async function kbRebuild() {
  const projectRoot = findProjectRoot();
  const pythonBin = resolvePython(projectRoot);
  const result = await spawnPythonAsync(
    pythonBin,
    ["-m", "video_extract2note.desktop_bridge", "kb-rebuild"],
    { cwd: projectRoot }
  );
  return interpretBridgeOutput(result);
}

async function kbSearch(query) {
  const projectRoot = findProjectRoot();
  const pythonBin = resolvePython(projectRoot);
  const result = await spawnPythonAsync(
    pythonBin,
    ["-m", "video_extract2note.desktop_bridge", "kb-search", String(query)],
    { cwd: projectRoot }
  );
  return interpretBridgeOutput(result);
}

async function listHistory(limit = 20, offset = 0) {
  const projectRoot = findProjectRoot();
  const pythonBin = resolvePython(projectRoot);
  const result = await spawnPythonAsync(
    pythonBin,
    ["-m", "video_extract2note.desktop_bridge", "list", String(limit), String(offset)],
    { cwd: projectRoot }
  );
  return interpretBridgeOutput(result);
}

async function searchRecords(query, limit = 10) {
  const trimmed = String(query).trim();
  if (!trimmed) {
    throw new Error("搜索关键词不能为空。");
  }
  const projectRoot = findProjectRoot();
  const pythonBin = resolvePython(projectRoot);
  const result = await spawnPythonAsync(
    pythonBin,
    ["-m", "video_extract2note.desktop_bridge", "search", trimmed, String(limit)],
    { cwd: projectRoot }
  );
  return interpretBridgeOutput(result);
}

async function getRecord(recordId) {
  const projectRoot = findProjectRoot();
  const pythonBin = resolvePython(projectRoot);
  const result = await spawnPythonAsync(
    pythonBin,
    ["-m", "video_extract2note.desktop_bridge", "get", String(recordId)],
    { cwd: projectRoot }
  );
  return interpretBridgeOutput(result);
}

function createWindow() {
  const isMac = process.platform === "darwin";

  const win = new BrowserWindow({
    width: 920,
    height: 720,
    minWidth: 480,
    minHeight: 560,
    ...(isMac
      ? {
          titleBarStyle: "hiddenInset",
          trafficLightPosition: { x: 16, y: 18 },
          transparent: true,
          backgroundColor: "#00000000",
          vibrancy: "under-window",
        }
      : {
          backgroundColor: "#0d0d12",
        }),
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      webviewTag: true,
    },
  });

  if (!app.isPackaged) {
    win.loadURL(DEV_URL);
  } else {
    win.loadFile(path.join(__dirname, "../dist/index.html"));
  }
}

/** 启动 FastAPI 后端服务 */
function startApiServer() {
  const projectRoot = findProjectRoot();
  const pythonBin = resolvePython(projectRoot);

  const apiProcess = spawn(pythonBin, ["-m", "video_extract2note.web_api"], {
    cwd: projectRoot,
    stdio: "pipe",
    env: {
      ...process.env,
      CORS_ORIGINS: "http://localhost:5173,http://127.0.0.1:5173",
    },
  });

  apiProcess.stdout.on("data", (data) => {
    console.log("[api]", data.toString().trim());
  });
  apiProcess.stderr.on("data", (data) => {
    console.log("[api]", data.toString().trim());
  });
  apiProcess.on("error", (err) => {
    console.error("[api] 启动失败:", err.message);
  });

  app.on("will-quit", () => {
    apiProcess.kill();
  });

  return apiProcess;
}

// 注册特权 scheme（必须在 app.whenReady 之前）
protocol.registerSchemesAsPrivileged([
  {
    scheme: "local-file",
    privileges: { stream: true, supportFetchAPI: true, bypassCSP: true },
  },
]);

app.whenReady().then(() => {
  startApiServer();

  // 安全地提供本地视频文件给渲染进程
  protocol.handle("local-file", (request) => {
    const pathPart = request.url.slice("local-file://".length);
    const filePath = decodeURIComponent(pathPart);

    let stat;
    try {
      stat = fs.statSync(filePath);
    } catch {
      return new Response("File not found", { status: 404 });
    }

    const fileSize = stat.size;
    const ext = path.extname(filePath).toLowerCase();
    const mimeTypes = {
      ".mp4": "video/mp4",
      ".m4a": "audio/mp4",
      ".mp3": "audio/mpeg",
      ".wav": "audio/wav",
    };
    const contentType = mimeTypes[ext] || "application/octet-stream";

    // 处理 Range 请求 — 纯 Buffer，不用 stream
    const rangeHeader = request.headers.get("range");
    if (rangeHeader) {
      const match = rangeHeader.match(/bytes=(\d+)-(\d*)/);
      if (match) {
        const start = parseInt(match[1], 10);
        const end = match[2] ? parseInt(match[2], 10) : fileSize - 1;
        const chunkSize = end - start + 1;

        const buf = Buffer.alloc(chunkSize);
        const fd = fs.openSync(filePath, "r");
        fs.readSync(fd, buf, 0, chunkSize, start);
        fs.closeSync(fd);

        return new Response(buf, {
          status: 206,
          headers: {
            "Content-Range": `bytes ${start}-${end}/${fileSize}`,
            "Accept-Ranges": "bytes",
            "Content-Length": String(chunkSize),
            "Content-Type": contentType,
          },
        });
      }
    }

    // 完整文件 — Buffer 一次读完
    const data = fs.readFileSync(filePath);
    return new Response(data, {
      headers: {
        "Content-Type": contentType,
        "Content-Length": String(fileSize),
        "Accept-Ranges": "bytes",
      },
    });
  });

  ipcMain.handle("transcribe-link", (_event, link) => transcribeLink(link));
  ipcMain.handle("transcribe-file", (_event, filePath) => transcribeFile(filePath));
  ipcMain.handle("pick-video-file", () => pickVideoFile());
  ipcMain.handle("search-videos", (_event, query, limit) => searchVideos(query, limit));
  ipcMain.handle("save-record", (_event, data) => saveRecord(data));
  ipcMain.handle("chat-send", (_event, messages, model) => chatSend(messages, model));
  ipcMain.handle("kb-rebuild", () => kbRebuild());
  ipcMain.handle("kb-search", (_event, query) => kbSearch(query));
  ipcMain.handle("list-history", (_event, limit, offset) => listHistory(limit, offset));
  ipcMain.handle("search-records", (_event, query, limit) => searchRecords(query, limit));
  ipcMain.handle("get-record", (_event, recordId) => getRecord(recordId));
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
