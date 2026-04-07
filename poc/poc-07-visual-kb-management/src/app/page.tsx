'use client';

import { useEffect } from 'react';
import { useKBStore } from '@/store/useKBStore';
import { KBCard } from '@/components/KBCard';
import { Loader2, Plus } from 'lucide-react';

export default function DashboardPage() {
  const { kbs, loading, fetchKBs } = useKBStore();

  useEffect(() => {
    fetchKBs();
  }, [fetchKBs]);

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Knowledge Bases</h1>
          <p className="text-sm text-gray-500">
            Manage your knowledge bases, documents, and chunks
          </p>
        </div>
        <button className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
          <Plus className="h-4 w-4" />
          Create KB
        </button>
      </div>

      {loading ? (
        <div className="mt-12 flex justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
        </div>
      ) : kbs.length === 0 ? (
        <div className="mt-12 text-center text-sm text-gray-400">
          No knowledge bases yet. Create one to get started.
        </div>
      ) : (
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {kbs.map((kb) => (
            <KBCard key={kb.id} kb={kb} />
          ))}
        </div>
      )}
    </div>
  );
}
