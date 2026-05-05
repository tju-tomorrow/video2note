/// <reference types="vite/client" />

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<object, object, unknown>;
  export default component;
}

declare module "vue-router" {
  interface RouteMeta {
    navTitle?: string;
    navDescription?: string;
    ready?: boolean;
    placeholderHint?: string;
    placeholderKicker?: string;
  }
}

type SearchResult = {
  title: string;
  url: string;
  platform: string;
  snippet: string;
};

type SearchResponse = {
  ok: boolean;
  results: SearchResult[];
  error?: string | null;
};

type BridgeResponse = {
  text: string;
  logs: string[];
  videoUrl?: string | null;
  timings?: { step: string; durationMs: number; status: string }[];
};

type RecordItem = {
  id: number;
  url: string;
  sourceType: string;
  platform: string;
  title: string;
  engine: string;
  duration: number | null;
  createdAt: string;
  preview: string;
};

type RecordDetail = RecordItem & {
  rawText: string;
  formattedText: string;
};

type ListResponse = {
  ok: boolean;
  records: RecordItem[];
  error?: string | null;
};

type DetailResponse = {
  ok: boolean;
  record: RecordDetail | null;
  error?: string | null;
};

declare global {
  interface Window {
    desktopBridge?: {
      transcribeLink: (link: string) => Promise<BridgeResponse>;
      transcribeFile: (filePath: string) => Promise<BridgeResponse>;
      pickVideoFile: () => Promise<string | null>;
      searchVideos: (query: string, limit?: number) => Promise<SearchResponse>;
      saveRecord: (data: Record<string, unknown>) => Promise<{ ok: boolean; error?: string | null }>;
      chatSend: (messages: Array<{ role: string; content: string }>, model: string) => Promise<{ ok: boolean; reply: string; error?: string | null }>;
      listHistory: (limit?: number, offset?: number) => Promise<ListResponse>;
      searchRecords: (query: string, limit?: number) => Promise<ListResponse>;
      getRecord: (recordId: number) => Promise<DetailResponse>;
    };
    appMeta?: {
      platform: string;
    };
  }
}

export {};
