/* API client for POC-09 backend (:8009) */

import type {
  ConnectorConfig,
  ConnectorWithSync,
  ContentListResponse,
  SourceInfo,
  SyncLog,
} from './types';

const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8009';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json();
}

/* ── Sources ────────────────────────────────────────────────────── */

export async function listSources(): Promise<SourceInfo[]> {
  const data = await request<{ sources: SourceInfo[] }>('/sources');
  return data.sources;
}

export async function getSource(type: string): Promise<SourceInfo> {
  return request<SourceInfo>(`/sources/${type}`);
}

/* ── Connectors ─────────────────────────────────────────────────── */

export async function listConnectors(sourceType?: string): Promise<ConnectorConfig[]> {
  const qs = sourceType ? `?source_type=${sourceType}` : '';
  const data = await request<{ connectors: ConnectorConfig[] }>(`/connectors${qs}`);
  return data.connectors;
}

export async function getConnector(id: string): Promise<ConnectorWithSync> {
  return request<ConnectorWithSync>(`/connectors/${id}`);
}

export async function createConnector(payload: {
  name: string;
  source_type: string;
  auth_method: string;
  credentials: Record<string, string>;
  config: Record<string, unknown>;
  kb_id?: string;
  refresh_interval_minutes?: number;
}): Promise<ConnectorWithSync> {
  return request<ConnectorWithSync>('/connectors', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function updateConnector(
  id: string,
  updates: Partial<ConnectorConfig>,
): Promise<{ connector: ConnectorConfig }> {
  return request<{ connector: ConnectorConfig }>(`/connectors/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(updates),
  });
}

export async function deleteConnector(id: string): Promise<void> {
  await request(`/connectors/${id}`, { method: 'DELETE' });
}

/* ── Sync ────────────────────────────────────────────────────────── */

export async function triggerSync(
  id: string,
  fullReindex = false,
): Promise<{ sync_log: SyncLog }> {
  return request<{ sync_log: SyncLog }>(
    `/connectors/${id}/sync?full_reindex=${fullReindex}`,
    { method: 'POST' },
  );
}

export async function cancelSync(id: string): Promise<void> {
  await request(`/connectors/${id}/cancel`, { method: 'POST' });
}

export async function getSyncLogs(id: string, limit = 20): Promise<SyncLog[]> {
  const data = await request<{ logs: SyncLog[] }>(`/connectors/${id}/logs?limit=${limit}`);
  return data.logs;
}

export async function getSyncStatus(id: string): Promise<{
  running: boolean;
  checkpoint: unknown;
  last_sync: SyncLog | null;
}> {
  return request(`/connectors/${id}/status`);
}

/* ── Browse ──────────────────────────────────────────────────────── */

export async function browseContent(
  id: string,
  path = '',
  cursor?: string,
  pageSize = 50,
): Promise<ContentListResponse> {
  const params = new URLSearchParams({ path, page_size: String(pageSize) });
  if (cursor) params.set('cursor', cursor);
  return request<ContentListResponse>(`/connectors/${id}/browse?${params}`);
}

/* ── Validate ────────────────────────────────────────────────────── */

export async function validateConnector(
  id: string,
): Promise<{ valid: boolean; error?: string }> {
  return request(`/connectors/${id}/validate`, { method: 'POST' });
}
