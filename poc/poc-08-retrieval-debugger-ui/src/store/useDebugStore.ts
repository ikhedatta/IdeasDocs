import { create } from 'zustand';
import type {
  DebugSearchResponse,
  CompareResponse,
  BatchResponse,
  RetrievalConfig,
  TestCase,
} from '@/lib/types';
import * as api from '@/lib/api';

interface DebugState {
  /* Search */
  searchResult: DebugSearchResponse | null;
  searchLoading: boolean;
  searchError: string | null;
  runSearch: (params: {
    query: string;
    kb_ids: string[];
    config: Partial<RetrievalConfig>;
  }) => Promise<void>;

  /* Compare */
  compareResult: CompareResponse | null;
  compareLoading: boolean;
  runCompare: (params: {
    query: string;
    kb_ids: string[];
    config_a: Partial<RetrievalConfig>;
    config_b: Partial<RetrievalConfig>;
  }) => Promise<void>;

  /* Batch */
  batchResult: BatchResponse | null;
  batchLoading: boolean;
  runBatch: (params: {
    kb_ids: string[];
    test_cases: TestCase[];
    config: Partial<RetrievalConfig>;
  }) => Promise<void>;
}

export const useDebugStore = create<DebugState>((set) => ({
  searchResult: null,
  searchLoading: false,
  searchError: null,

  runSearch: async ({ query, kb_ids, config }) => {
    set({ searchLoading: true, searchError: null });
    try {
      const result = await api.debugSearch({ query, kb_ids, ...config });
      set({ searchResult: result });
    } catch (e: any) {
      set({ searchError: e.message });
    } finally {
      set({ searchLoading: false });
    }
  },

  compareResult: null,
  compareLoading: false,

  runCompare: async ({ query, kb_ids, config_a, config_b }) => {
    set({ compareLoading: true });
    try {
      const result = await api.compareConfigs({ query, kb_ids, config_a, config_b });
      set({ compareResult: result });
    } finally {
      set({ compareLoading: false });
    }
  },

  batchResult: null,
  batchLoading: false,

  runBatch: async ({ kb_ids, test_cases, config }) => {
    set({ batchLoading: true });
    try {
      const result = await api.batchTest({ kb_ids, test_cases, ...config });
      set({ batchResult: result });
    } finally {
      set({ batchLoading: false });
    }
  },
}));
