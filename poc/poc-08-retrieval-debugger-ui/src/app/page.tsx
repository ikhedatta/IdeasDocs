'use client';

import { useState } from 'react';
import { useDebugStore } from '@/store/useDebugStore';
import { QueryInput } from '@/components/QueryInput';
import { ConfigPanel } from '@/components/ConfigPanel';
import { ResultCard } from '@/components/ResultCard';
import { TimingBar } from '@/components/TimingBar';
import type { RetrievalConfig } from '@/lib/types';
import { AlertCircle, Layers } from 'lucide-react';

export default function SearchPage() {
  const [config, setConfig] = useState<Partial<RetrievalConfig>>({
    top_k: 20,
    final_k: 10,
    similarity_threshold: 0,
    dense_weight: 0.7,
    sparse_weight: 0.3,
    rerank_model: null,
  });

  const { searchResult, searchLoading, searchError, runSearch } =
    useDebugStore();

  const handleSearch = (query: string, kbIds: string[]) => {
    runSearch({ query, kb_ids: kbIds, config });
  };

  return (
    <div>
      <h1 className="text-xl font-bold text-gray-900">Debug Search</h1>
      <p className="text-sm text-gray-500">
        Test retrieval with full score decomposition and timing breakdown
      </p>

      <div className="mt-6 space-y-4">
        <QueryInput onSearch={handleSearch} loading={searchLoading} />
        <ConfigPanel config={config} onChange={setConfig} />
      </div>

      {/* Error */}
      {searchError && (
        <div className="mt-4 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <AlertCircle className="h-4 w-4" />
          {searchError}
        </div>
      )}

      {/* Results */}
      {searchResult && (
        <div className="mt-6 space-y-4">
          {/* Summary */}
          <div className="flex items-center gap-4 text-sm text-gray-600">
            <span className="flex items-center gap-1">
              <Layers className="h-4 w-4" />
              {searchResult.final_count} results
            </span>
            <span className="text-gray-400">
              ({searchResult.total_candidates} candidates → {searchResult.after_threshold} after threshold → {searchResult.final_count} final)
            </span>
          </div>

          {/* Timing */}
          <TimingBar timings={searchResult.timings_ms} />

          {/* Result Cards */}
          <div className="space-y-3">
            {searchResult.results.map((r) => (
              <ResultCard key={r.chunk_id} result={r} />
            ))}
          </div>

          {searchResult.results.length === 0 && (
            <div className="py-8 text-center text-sm text-gray-400">
              No results found. Try lowering the threshold or adjusting weights.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
