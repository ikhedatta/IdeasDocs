/* API client for retrieval debug endpoints (POC-05) */

import type {
  DebugSearchResponse,
  CompareResponse,
  BatchResponse,
  RetrievalConfig,
  TestCase,
} from './types';

const API_URL =
  process.env.NEXT_PUBLIC_DEBUG_API_URL || 'http://localhost:8005';

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

export async function debugSearch(params: {
  query: string;
  kb_ids: string[];
  top_k?: number;
  final_k?: number;
  similarity_threshold?: number;
  dense_weight?: number;
  sparse_weight?: number;
  rerank_model?: string | null;
}): Promise<DebugSearchResponse> {
  return post('/debug/search', params);
}

export async function compareConfigs(params: {
  query: string;
  kb_ids: string[];
  config_a: Partial<RetrievalConfig>;
  config_b: Partial<RetrievalConfig>;
}): Promise<CompareResponse> {
  return post('/debug/compare', params);
}

export async function batchTest(params: {
  kb_ids: string[];
  test_cases: TestCase[];
  top_k?: number;
  final_k?: number;
  dense_weight?: number;
  sparse_weight?: number;
}): Promise<BatchResponse> {
  return post('/debug/batch', params);
}
