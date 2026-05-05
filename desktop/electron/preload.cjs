const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("desktopBridge", {
  transcribeLink: (link) => ipcRenderer.invoke("transcribe-link", link),
  transcribeFile: (filePath) => ipcRenderer.invoke("transcribe-file", filePath),
  pickVideoFile: () => ipcRenderer.invoke("pick-video-file"),
  searchVideos: (query, limit) => ipcRenderer.invoke("search-videos", query, limit),
  saveRecord: (data) => ipcRenderer.invoke("save-record", data),
  chatSend: (messages, model) => ipcRenderer.invoke("chat-send", messages, model),
  kbRebuild: () => ipcRenderer.invoke("kb-rebuild"),
  kbSearch: (query) => ipcRenderer.invoke("kb-search", query),
  listHistory: (limit, offset) => ipcRenderer.invoke("list-history", limit, offset),
  searchRecords: (query, limit) => ipcRenderer.invoke("search-records", query, limit),
  getRecord: (recordId) => ipcRenderer.invoke("get-record", recordId),
});

contextBridge.exposeInMainWorld("appMeta", {
  platform: process.platform,
});
