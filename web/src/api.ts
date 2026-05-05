const BASE = "http://127.0.0.1:8765";

async function post(path: string, body: any) {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

export const api = {
  extract: (url: string) => post("/api/extract", { url }),
  extractFile: (filePath: string) => post("/api/extract-file", { file_path: filePath }),
  chat: (messages: any[], model: string) => post("/api/chat", { messages, model }),
  save: (data: any) => post("/api/save", data),
  history: (limit = 20) => fetch(`${BASE}/api/history?limit=${limit}`).then((r) => r.json()),
  search: (query: string) => post("/api/search", { query }),
  get: (id: number) => fetch(`${BASE}/api/history/${id}`).then((r) => r.json()),
  kbRebuild: () => post("/api/knowledge/rebuild", {}),
  kbSearch: (query: string) => post("/api/knowledge/search", { query }),
  kbStatus: () => fetch(`${BASE}/api/knowledge/status`).then((r) => r.json()),
};
