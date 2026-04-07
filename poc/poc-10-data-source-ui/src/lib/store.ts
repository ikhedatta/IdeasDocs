/* Zustand store for data source management state */

import { create } from 'zustand';
import type { ConnectorConfig, ConnectorWithSync, SourceInfo, SyncLog, ContentItem } from './types';
import * as api from './api';

interface DataSourceState {
  /* Sources catalog */
  sources: SourceInfo[];
  sourcesLoading: boolean;
  loadSources: () => Promise<void>;

  /* Connectors */
  connectors: ConnectorConfig[];
  connectorsLoading: boolean;
  loadConnectors: (sourceType?: string) => Promise<void>;

  /* Active connector detail */
  activeConnector: ConnectorWithSync | null;
  activeLoading: boolean;
  loadConnector: (id: string) => Promise<void>;

  /* Sync logs for active connector */
  syncLogs: SyncLog[];
  loadSyncLogs: (id: string) => Promise<void>;

  /* Content browser */
  browseItems: ContentItem[];
  browsePath: string;
  browseLoading: boolean;
  browseContent: (id: string, path?: string) => Promise<void>;

  /* Actions */
  createConnector: (payload: Parameters<typeof api.createConnector>[0]) => Promise<ConnectorWithSync>;
  deleteConnector: (id: string) => Promise<void>;
  triggerSync: (id: string, full?: boolean) => Promise<void>;
  cancelSync: (id: string) => Promise<void>;
  validateConnector: (id: string) => Promise<{ valid: boolean; error?: string }>;
}

export const useDataSourceStore = create<DataSourceState>((set, get) => ({
  /* Sources */
  sources: [],
  sourcesLoading: false,
  loadSources: async () => {
    set({ sourcesLoading: true });
    try {
      const sources = await api.listSources();
      set({ sources });
    } finally {
      set({ sourcesLoading: false });
    }
  },

  /* Connectors */
  connectors: [],
  connectorsLoading: false,
  loadConnectors: async (sourceType?: string) => {
    set({ connectorsLoading: true });
    try {
      const connectors = await api.listConnectors(sourceType);
      set({ connectors });
    } finally {
      set({ connectorsLoading: false });
    }
  },

  /* Active connector */
  activeConnector: null,
  activeLoading: false,
  loadConnector: async (id: string) => {
    set({ activeLoading: true });
    try {
      const data = await api.getConnector(id);
      set({ activeConnector: data });
    } finally {
      set({ activeLoading: false });
    }
  },

  /* Sync logs */
  syncLogs: [],
  loadSyncLogs: async (id: string) => {
    const logs = await api.getSyncLogs(id);
    set({ syncLogs: logs });
  },

  /* Content browser */
  browseItems: [],
  browsePath: '',
  browseLoading: false,
  browseContent: async (id: string, path = '') => {
    set({ browseLoading: true, browsePath: path });
    try {
      const data = await api.browseContent(id, path);
      set({ browseItems: data.items });
    } finally {
      set({ browseLoading: false });
    }
  },

  /* Actions */
  createConnector: async (payload) => {
    const result = await api.createConnector(payload);
    await get().loadConnectors();
    return result;
  },

  deleteConnector: async (id: string) => {
    await api.deleteConnector(id);
    set({ activeConnector: null });
    await get().loadConnectors();
  },

  triggerSync: async (id: string, full = false) => {
    await api.triggerSync(id, full);
    // Refresh after short delay for status
    setTimeout(() => get().loadConnector(id), 1000);
  },

  cancelSync: async (id: string) => {
    await api.cancelSync(id);
    await get().loadConnector(id);
  },

  validateConnector: async (id: string) => {
    return api.validateConnector(id);
  },
}));
