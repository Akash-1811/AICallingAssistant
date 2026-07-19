import { apiDelete, apiFormPost, apiGet, apiPost } from "./conversations";

export type KnowledgeSource = {
  id: string;
  filename: string;
  file_type: string;
  file_size: number;
  status: "processing" | "ready" | "failed";
  chunk_count: number;
  error: string | null;
  created_at: string | null;
  synced_at: string | null;
};

export type KnowledgeList = {
  items: KnowledgeSource[];
  total_bytes: number;
};

export const listKnowledgeSources = () =>
  apiGet<KnowledgeList>("/api/v1/knowledge/sources");

export const uploadKnowledgeFile = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return apiFormPost<KnowledgeSource>("/api/v1/knowledge/upload", form);
};

export const syncKnowledgeSource = (id: string) =>
  apiPost<KnowledgeSource>(`/api/v1/knowledge/sources/${id}/sync`);

export const syncAllKnowledge = () =>
  apiPost<{ queued: number }>("/api/v1/knowledge/sync-all");

export const deleteKnowledgeSource = (id: string) =>
  apiDelete(`/api/v1/knowledge/sources/${id}`);
