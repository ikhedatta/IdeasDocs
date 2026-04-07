/**
 * POC-10 — Zustand Store tests (mock api module)
 */

jest.mock('../lib/api');

import * as api from '../lib/api';
import { useDataSourceStore } from '../lib/store';

const mockedApi = api as jest.Mocked<typeof api>;

describe('Zustand Store', () => {
  beforeEach(() => {
    // Reset store state
    useDataSourceStore.setState({
      sources: [],
      sourcesLoading: false,
      connectors: [],
      connectorsLoading: false,
      activeConnector: null,
      activeLoading: false,
      syncLogs: [],
      browseItems: [],
      browsePath: '',
      browseLoading: false,
    });
    jest.clearAllMocks();
  });

  test('initial state has empty arrays', () => {
    const state = useDataSourceStore.getState();
    expect(state.sources).toEqual([]);
    expect(state.connectors).toEqual([]);
    expect(state.syncLogs).toEqual([]);
    expect(state.browseItems).toEqual([]);
    expect(state.activeConnector).toBeNull();
  });

  test('loadSources fetches and sets sources', async () => {
    const mockSources = [{ source_type: 'github', display_name: 'GitHub' }] as any;
    mockedApi.listSources.mockResolvedValueOnce(mockSources);

    await useDataSourceStore.getState().loadSources();
    const state = useDataSourceStore.getState();

    expect(state.sources).toEqual(mockSources);
    expect(state.sourcesLoading).toBe(false);
    expect(mockedApi.listSources).toHaveBeenCalledTimes(1);
  });

  test('loadConnectors fetches and sets connectors', async () => {
    const mockConnectors = [{ id: 'c1', name: 'Test' }] as any;
    mockedApi.listConnectors.mockResolvedValueOnce(mockConnectors);

    await useDataSourceStore.getState().loadConnectors();
    expect(useDataSourceStore.getState().connectors).toEqual(mockConnectors);
  });

  test('loadConnectors passes source type filter', async () => {
    mockedApi.listConnectors.mockResolvedValueOnce([]);
    await useDataSourceStore.getState().loadConnectors('github');
    expect(mockedApi.listConnectors).toHaveBeenCalledWith('github');
  });

  test('loadConnector fetches and sets activeConnector', async () => {
    const mockData = { connector: { id: 'c1' }, last_sync: null } as any;
    mockedApi.getConnector.mockResolvedValueOnce(mockData);

    await useDataSourceStore.getState().loadConnector('c1');
    expect(useDataSourceStore.getState().activeConnector).toEqual(mockData);
    expect(useDataSourceStore.getState().activeLoading).toBe(false);
  });

  test('loadSyncLogs sets syncLogs', async () => {
    const mockLogs = [{ id: 'l1', status: 'done' }] as any;
    mockedApi.getSyncLogs.mockResolvedValueOnce(mockLogs);

    await useDataSourceStore.getState().loadSyncLogs('c1');
    expect(useDataSourceStore.getState().syncLogs).toEqual(mockLogs);
  });

  test('browseContent sets items and path', async () => {
    const mockData = { items: [{ id: '1', name: 'file.pdf' }], has_more: false };
    mockedApi.browseContent.mockResolvedValueOnce(mockData as any);

    await useDataSourceStore.getState().browseContent('c1', '/docs');
    const state = useDataSourceStore.getState();
    expect(state.browseItems).toHaveLength(1);
    expect(state.browsePath).toBe('/docs');
    expect(state.browseLoading).toBe(false);
  });

  test('deleteConnector clears activeConnector and reloads list', async () => {
    mockedApi.deleteConnector.mockResolvedValueOnce(undefined as any);
    mockedApi.listConnectors.mockResolvedValueOnce([]);

    // Set active first
    useDataSourceStore.setState({ activeConnector: { connector: { id: 'c1' } } as any });
    await useDataSourceStore.getState().deleteConnector('c1');

    expect(useDataSourceStore.getState().activeConnector).toBeNull();
    expect(mockedApi.listConnectors).toHaveBeenCalled();
  });

  test('loading flags are set during load and cleared after', async () => {
    let resolve: (v: any) => void;
    mockedApi.listSources.mockReturnValueOnce(new Promise(r => { resolve = r; }));

    const loadPromise = useDataSourceStore.getState().loadSources();
    expect(useDataSourceStore.getState().sourcesLoading).toBe(true);

    resolve!([]);
    await loadPromise;
    expect(useDataSourceStore.getState().sourcesLoading).toBe(false);
  });

  test('loading flags cleared even on error', async () => {
    mockedApi.listSources.mockRejectedValueOnce(new Error('fail'));

    try {
      await useDataSourceStore.getState().loadSources();
    } catch {
      // expected
    }
    expect(useDataSourceStore.getState().sourcesLoading).toBe(false);
  });

  test('createConnector calls api and reloads list', async () => {
    const mockResult = { connector: { id: 'new-1' } } as any;
    mockedApi.createConnector.mockResolvedValueOnce(mockResult);
    mockedApi.listConnectors.mockResolvedValueOnce([]);

    const payload = {
      name: 'New', source_type: 'github', auth_method: 'api_key',
      credentials: { api_token: 'x' }, config: { repos: ['a/b'] },
    };
    const result = await useDataSourceStore.getState().createConnector(payload);
    expect(result.connector.id).toBe('new-1');
    expect(mockedApi.createConnector).toHaveBeenCalledWith(payload);
    expect(mockedApi.listConnectors).toHaveBeenCalled();
  });
});
