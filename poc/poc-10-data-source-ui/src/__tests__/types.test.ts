/**
 * POC-10 — Types & Constants tests
 */

import { CATEGORIES } from '../lib/types';
import type {
  AuthMethod,
  ConnectorConfig,
  ConnectorStatus,
  ContentItem,
  ContentListResponse,
  SourceInfo,
  SourceType,
  SyncLog,
  SyncStatus,
} from '../lib/types';

describe('Types & Constants', () => {
  test('CATEGORIES has all 5 categories', () => {
    const keys = Object.keys(CATEGORIES);
    expect(keys).toHaveLength(5);
    expect(keys).toContain('cloud_storage');
    expect(keys).toContain('collaboration');
    expect(keys).toContain('communication');
    expect(keys).toContain('dev_tools');
    expect(keys).toContain('project_management');
  });

  test('each category has label and color', () => {
    for (const [, val] of Object.entries(CATEGORIES)) {
      expect(val.label).toBeTruthy();
      expect(val.color).toBeTruthy();
      expect(typeof val.label).toBe('string');
      expect(val.color).toMatch(/^bg-/);
    }
  });

  test('SourceInfo type can be constructed', () => {
    const info: SourceInfo = {
      source_type: 's3' as SourceType,
      display_name: 'Amazon S3',
      description: 'Test',
      icon: 'cloud',
      category: 'cloud_storage',
      auth_methods: ['access_key' as AuthMethod],
      default_auth: 'access_key' as AuthMethod,
      config_schema: { bucket: { type: 'string', required: true } },
    };
    expect(info.display_name).toBe('Amazon S3');
    expect(info.auth_methods).toHaveLength(1);
  });

  test('ConnectorConfig type can be constructed', () => {
    const config: ConnectorConfig = {
      id: 'test-id', name: 'My S3', source_type: 's3' as SourceType,
      auth_method: 'access_key' as AuthMethod, credentials: { access_key_id: 'AKIA...' },
      config: { bucket: 'test' }, status: 'active' as ConnectorStatus,
      refresh_interval_minutes: 60, timeout_seconds: 600,
      created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z',
    };
    expect(config.id).toBe('test-id');
    expect(config.status).toBe('active');
  });

  test('SyncLog type can be constructed', () => {
    const log: SyncLog = {
      id: 'log-1', connector_id: 'conn-1', status: 'done' as SyncStatus,
      docs_fetched: 100, docs_new: 50, docs_updated: 25, docs_failed: 0,
    };
    expect(log.docs_fetched).toBe(100);
    expect(log.error_message).toBeUndefined();
  });

  test('ContentItem type can be constructed', () => {
    const item: ContentItem = {
      id: 'folder-1', name: 'Documents', path: '/Documents',
      item_type: 'folder', selectable: true, metadata: {},
    };
    expect(item.name).toBe('Documents');
  });

  test('ContentListResponse type can be constructed', () => {
    const resp: ContentListResponse = { items: [], has_more: false };
    expect(resp.items).toHaveLength(0);
    expect(resp.cursor).toBeUndefined();
  });

  test('all 13 source types are valid string literals', () => {
    const types: SourceType[] = [
      's3', 'confluence', 'discord', 'google_drive', 'gmail',
      'jira', 'dropbox', 'gcs', 'gitlab', 'github',
      'bitbucket', 'zendesk', 'asana',
    ];
    expect(types).toHaveLength(13);
  });
});
