import { create } from 'zustand';
import type { KnowledgeBase, KBStats, Document, Chunk } from '@/lib/types';
import * as api from '@/lib/api';

interface KBState {
  /* data */
  kbs: KnowledgeBase[];
  currentKB: KnowledgeBase | null;
  stats: KBStats | null;
  documents: Document[];
  chunks: Chunk[];
  chunkTotal: number;
  chunkPage: number;

  /* loading */
  loading: boolean;

  /* actions */
  fetchKBs: () => Promise<void>;
  fetchKB: (id: string) => Promise<void>;
  fetchStats: (id: string) => Promise<void>;
  fetchDocuments: (kbId: string) => Promise<void>;
  fetchChunks: (params: {
    kb_id: string;
    document_id?: string;
    status?: string;
    keyword?: string;
    page?: number;
  }) => Promise<void>;
  toggleChunk: (kbId: string, chunkId: string, active: boolean) => Promise<void>;
  updateChunk: (kbId: string, chunkId: string, content: string) => Promise<void>;
}

export const useKBStore = create<KBState>((set, get) => ({
  kbs: [],
  currentKB: null,
  stats: null,
  documents: [],
  chunks: [],
  chunkTotal: 0,
  chunkPage: 1,
  loading: false,

  fetchKBs: async () => {
    set({ loading: true });
    try {
      const kbs = await api.listKBs();
      set({ kbs });
    } finally {
      set({ loading: false });
    }
  },

  fetchKB: async (id) => {
    set({ loading: true });
    try {
      const kb = await api.getKB(id);
      set({ currentKB: kb });
    } finally {
      set({ loading: false });
    }
  },

  fetchStats: async (id) => {
    const stats = await api.getKBStats(id);
    set({ stats });
  },

  fetchDocuments: async (kbId) => {
    const { documents } = await api.listDocuments(kbId);
    set({ documents });
  },

  fetchChunks: async (params) => {
    set({ loading: true });
    try {
      const res = await api.listChunks({ ...params, page_size: 20 });
      set({ chunks: res.chunks, chunkTotal: res.total, chunkPage: params.page ?? 1 });
    } finally {
      set({ loading: false });
    }
  },

  toggleChunk: async (kbId, chunkId, active) => {
    await api.toggleChunk(kbId, chunkId, active);
    set((s) => ({
      chunks: s.chunks.map((c) =>
        c.chunk_id === chunkId ? { ...c, is_active: active } : c,
      ),
    }));
  },

  updateChunk: async (kbId, chunkId, content) => {
    const updated = await api.updateChunk(kbId, chunkId, content);
    set((s) => ({
      chunks: s.chunks.map((c) => (c.chunk_id === chunkId ? updated : c)),
    }));
  },
}));
