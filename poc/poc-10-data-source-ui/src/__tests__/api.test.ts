/**
 * POC-10 — API Client tests (mock global fetch)
 */

import type { ConnectorConfig } from '../lib/types';

// Mock global fetch before importing api module
const mockFetch = jest.fn();
(global as any).fetch = mockFetch;

function mockJsonResponse(data: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(data),
    text: () => Promise.resolve(JSON.stringify(data)),
  } as Response);
}

// Import api AFTER mocking fetch
import * as api from '../lib/api';

describe('API Client', () => {
  beforeEach(() => {
    mockFetch.mockClear();
  });

  test('listSources calls /sources and returns sources array', async () => {
    const mockSources = [{ source_type: 'github', display_name: 'GitHub' }];
    mockFetch.mockReturnValueOnce(mockJsonResponse({ sources: mockSources }));

    const result = await api.listSources();
    expect(result).toEqual(mockSources);
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/sources'),
      expect.objectContaining({ headers: expect.any(Object) }),
    );
  });

  test('getSource calls /sources/{type}', async () => {
    const mockSource = { source_type: 'github', display_name: 'GitHub' };
    mockFetch.mockReturnValueOnce(mockJsonResponse(mockSource));

    const result = await api.getSource('github');
    expect(result.display_name).toBe('GitHub');
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/sources/github'),
      expect.any(Object),
    );
  });

  test('listConnectors calls /connectors', async () => {
    mockFetch.mockReturnValueOnce(mockJsonResponse({ connectors: [], total: 0 }));
    const result = await api.listConnectors();
    expect(result).toEqual([]);
  });

  test('listConnectors with filter passes query param', async () => {
    mockFetch.mockReturnValueOnce(mockJsonResponse({ connectors: [], total: 0 }));
    await api.listConnectors('github');
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('source_type=github'),
      expect.any(Object),
    );
  });

  test('getConnector calls /connectors/{id}', async () => {
    const mockData = { connector: { id: 'c1', name: 'Test' }, last_sync: null };
    mockFetch.mockReturnValueOnce(mockJsonResponse(mockData));
    const result = await api.getConnector('c1');
    expect(result.connector.id).toBe('c1');
  });

  test('createConnector sends POST to /connectors', async () => {
    const mockResult = { connector: { id: 'new-1', name: 'New' }, source_info: {} };
    mockFetch.mockReturnValueOnce(mockJsonResponse(mockResult));

    const payload = {
      name: 'New', source_type: 'github', auth_method: 'api_key',
      credentials: { api_token: 'x' }, config: { repos: ['a/b'] },
    };
    const result = await api.createConnector(payload);
    expect(result.connector.name).toBe('New');

    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toContain('/connectors');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual(payload);
  });

  test('updateConnector sends PATCH', async () => {
    mockFetch.mockReturnValueOnce(mockJsonResponse({ connector: { id: 'c1', name: 'Renamed' } }));
    const result = await api.updateConnector('c1', { name: 'Renamed' } as Partial<ConnectorConfig>);
    expect(result.connector.name).toBe('Renamed');

    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toContain('/connectors/c1');
    expect(init.method).toBe('PATCH');
  });

  test('deleteConnector sends DELETE', async () => {
    mockFetch.mockReturnValueOnce(mockJsonResponse({ deleted: true }));
    await api.deleteConnector('c1');
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toContain('/connectors/c1');
    expect(init.method).toBe('DELETE');
  });

  test('triggerSync sends POST with full_reindex param', async () => {
    mockFetch.mockReturnValueOnce(mockJsonResponse({ sync_log: { id: 'l1', status: 'scheduled' } }));
    const result = await api.triggerSync('c1', true);
    expect(result.sync_log.status).toBe('scheduled');

    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toContain('/connectors/c1/sync');
    expect(url).toContain('full_reindex=true');
    expect(init.method).toBe('POST');
  });

  test('cancelSync sends POST to cancel endpoint', async () => {
    mockFetch.mockReturnValueOnce(mockJsonResponse({ cancelled: true }));
    await api.cancelSync('c1');
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toContain('/connectors/c1/cancel');
    expect(init.method).toBe('POST');
  });

  test('getSyncLogs fetches logs with limit', async () => {
    mockFetch.mockReturnValueOnce(mockJsonResponse({ logs: [{ id: 'l1' }], total: 1 }));
    const result = await api.getSyncLogs('c1', 10);
    expect(result).toHaveLength(1);
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('limit=10'),
      expect.any(Object),
    );
  });

  test('getSyncStatus returns status object', async () => {
    mockFetch.mockReturnValueOnce(mockJsonResponse({ running: false, checkpoint: null, last_sync: null }));
    const result = await api.getSyncStatus('c1');
    expect(result.running).toBe(false);
  });

  test('browseContent passes path, cursor, and pageSize params', async () => {
    mockFetch.mockReturnValueOnce(mockJsonResponse({ items: [], has_more: false }));
    await api.browseContent('c1', '/docs', 'cursor123', 25);
    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain('path=%2Fdocs');
    expect(url).toContain('cursor=cursor123');
    expect(url).toContain('page_size=25');
  });

  test('request throws on non-ok response', async () => {
    mockFetch.mockReturnValueOnce(
      Promise.resolve({ ok: false, status: 404, text: () => Promise.resolve('Not found') } as Response),
    );
    await expect(api.listSources()).rejects.toThrow('404');
  });
});
