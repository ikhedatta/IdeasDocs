/* Types for POC-10 Data Source Management UI */

export type SourceType =
  | 's3'
  | 'confluence'
  | 'discord'
  | 'google_drive'
  | 'gmail'
  | 'jira'
  | 'dropbox'
  | 'gcs'
  | 'gitlab'
  | 'github'
  | 'bitbucket'
  | 'zendesk'
  | 'asana';

export type AuthMethod =
  | 'api_key'
  | 'oauth2'
  | 'access_key'
  | 'service_account'
  | 'bot_token'
  | 'basic'
  | 'app_password';

export type ConnectorStatus = 'active' | 'paused' | 'error' | 'disconnected';
export type SyncStatus = 'idle' | 'scheduled' | 'running' | 'done' | 'failed' | 'cancelled';

export interface SourceInfo {
  source_type: SourceType;
  display_name: string;
  description: string;
  icon: string;
  category: string;
  auth_methods: AuthMethod[];
  default_auth: AuthMethod;
  config_schema: Record<string, ConfigField>;
}

export interface ConfigField {
  type: string;
  required?: boolean;
  description?: string;
  default?: unknown;
  items?: string;
}

export interface ConnectorConfig {
  id: string;
  name: string;
  source_type: SourceType;
  auth_method: AuthMethod;
  credentials: Record<string, string>;
  config: Record<string, unknown>;
  kb_id?: string;
  status: ConnectorStatus;
  refresh_interval_minutes: number;
  timeout_seconds: number;
  created_at: string;
  updated_at: string;
}

export interface SyncLog {
  id: string;
  connector_id: string;
  status: SyncStatus;
  started_at?: string;
  finished_at?: string;
  docs_fetched: number;
  docs_new: number;
  docs_updated: number;
  docs_failed: number;
  error_message?: string;
}

export interface SyncCheckpoint {
  last_sync_start?: string;
  last_sync_end?: string;
  cursor?: string;
}

export interface ContentItem {
  id: string;
  name: string;
  path: string;
  item_type: string;
  size_bytes?: number;
  updated_at?: string;
  children_count?: number;
  selectable: boolean;
  metadata: Record<string, unknown>;
}

export interface ContentListResponse {
  items: ContentItem[];
  cursor?: string;
  has_more: boolean;
}

export interface ConnectorWithSync {
  connector: ConnectorConfig;
  last_sync?: SyncLog;
  source_info?: SourceInfo;
}

/* Category metadata */
export const CATEGORIES: Record<string, { label: string; color: string }> = {
  cloud_storage: { label: 'Cloud Storage', color: 'bg-blue-100 text-blue-700' },
  collaboration: { label: 'Collaboration', color: 'bg-purple-100 text-purple-700' },
  communication: { label: 'Communication', color: 'bg-green-100 text-green-700' },
  dev_tools: { label: 'Dev Tools', color: 'bg-orange-100 text-orange-700' },
  project_management: { label: 'Project Mgmt', color: 'bg-pink-100 text-pink-700' },
};
