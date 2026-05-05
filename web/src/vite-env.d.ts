/// <reference types="vite/client" />

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<object, object, unknown>;
  export default component;
}

type SearchResult = {
  title: string;
  url: string;
  platform: string;
  snippet: string;
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

declare global {
  interface Window {
    vidwiseAPI?: {
      extract: (url: string) => Promise<any>;
      chat: (messages: any[], model: string) => Promise<any>;
      save: (data: any) => Promise<any>;
      history: (limit?: number) => Promise<any>;
      search: (query: string) => Promise<any>;
    };
  }
}

export {};
