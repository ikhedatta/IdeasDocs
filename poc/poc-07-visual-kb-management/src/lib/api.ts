/* API client for KB and chunk management backends */

import type {
  KnowledgeBase,
  KBStats,
  Document,
  Chunk,
  ChunkListResponse,
} from './types';

const KB_API = process.env.NEXT_PUBLIC_KB_API_URL || 'http://localhost:8006';
const CHUNK_API =
  process.env.NEXT_PUBLIC_CHUNK_API_URL || 'http://localhost:8004';

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json();
}

/* ── Knowledge Bases ─────────────────────────────────── */

export async function listKBs(): Promise<KnowledgeBase[]> {
  return fetchJSON<KnowledgeBase[]>(`${KB_API}/kb`);
}

export async function getKB(kbId: string): Promise<KnowledgeBase> {
  return fetchJSON<KnowledgeBase>(`${KB_API}/kb/${kbId}`);
}

export async function getKBStats(kbId: string): Promise<KBStats> {
  return fetchJSON<KBStats>(`${KB_API}/kb/${kbId}/stats`);
}

export async function createKB(data: {
  name: string;
  description?: string;
  tags?: string[];
}): Promise<KnowledgeBase> {
  return fetchJSON<KnowledgeBase>(`${KB_API}/kb`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function deleteKB(kbId: string): Promise<void> {
  await fetchJSON(`${KB_API}/kb/${kbId}`, { method: 'DELETE' });
}

/* ── Documents ───────────────────────────────────────── */

export async function listDocuments(
  kbId: string,
): Promise<{ total: number; documents: Document[] }> {
  return fetchJSON(`${KB_API}/kb/${kbId}/documents`);
}

export async function uploadDocument(
  kbId: string,
  file: File,
): Promise<Document> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${KB_API}/kb/${kbId}/documents/upload`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  return res.json();
}

export async function deleteDocument(
  kbId: string,
  docId: string,
): Promise<void> {
  await fetchJSON(`${KB_API}/kb/${kbId}/documents/${docId}`, {
    method: 'DELETE',
  });
}

/* ── Chunks ──────────────────────────────────────────── */

export async function listChunks(params: {
  kb_id: string;
  document_id?: string;
  status?: string;
  keyword?: string;
  page?: number;
  page_size?: number;
}): Promise<ChunkListResponse> {
  const sp = new URLSearchParams();
  sp.set('kb_id', params.kb_id);
  if (params.document_id) sp.set('document_id', params.document_id);
  if (params.status) sp.set('status', params.status);
  if (params.keyword) sp.set('keyword', params.keyword);
  sp.set('page', String(params.page ?? 1));
  sp.set('page_size', String(params.page_size ?? 20));
  return fetchJSON<ChunkListResponse>(`${CHUNK_API}/chunks?${sp}`);
}

export async function getChunk(
  kbId: string,
  chunkId: string,
): Promise<Chunk> {
  return fetchJSON<Chunk>(`${CHUNK_API}/chunks/${chunkId}?kb_id=${kbId}`);
}

export async function toggleChunk(
  kbId: string,
  chunkId: string,
  isActive: boolean,
): Promise<void> {
  await fetchJSON(`${CHUNK_API}/chunks/${chunkId}/toggle?kb_id=${kbId}`, {
    method: 'PATCH',
    body: JSON.stringify({ is_active: isActive }),
  });
}

export async function updateChunk(
  kbId: string,
  chunkId: string,
  content: string,
): Promise<Chunk> {
  return fetchJSON<Chunk>(`${CHUNK_API}/chunks/${chunkId}?kb_id=${kbId}`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  });
}

export async function createChunk(data: {
  kb_id: string;
  content: string;
  document_name?: string;
}): Promise<Chunk> {
  return fetchJSON<Chunk>(`${CHUNK_API}/chunks`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function batchChunkAction(data: {
  kb_id: string;
  chunk_ids: string[];
  action: 'enable' | 'disable' | 'delete';
}): Promise<{ succeeded: number; failed: number }> {
  return fetchJSON(`${CHUNK_API}/chunks/batch`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}
