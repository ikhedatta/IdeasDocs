'use client';

import { useState } from 'react';
import { useDebugStore } from '@/store/useDebugStore';
import { QueryInput } from '@/components/QueryInput';
import { ConfigPanel } from '@/components/ConfigPanel';
import { ResultCard } from '@/components/ResultCard';
import { TimingBar } from '@/components/TimingBar';
import { OverlapBadge } from '@/components/OverlapBadge';
import type { RetrievalConfig } from '@/lib/types';
import { Loader2 } from 'lucide-react';

export default function ComparePage() {
  const [configA, setConfigA] = useState<Partial<RetrievalConfig>>({
    top_k: 20,
    final_k: 10,
    dense_weight: 0.7,
    sparse_weight: 0.3,
    rerank_model: null,
  });
  const [configB, setConfigB] = useState<Partial<RetrievalConfig>>({
    top_k: 20,
    final_k: 10,
    dense_weight: 0.3,
    sparse_weight: 0.7,
    rerank_model: null,
  });

  const { compareResult, compareLoading, runCompare } = useDebugStore();

  const handleSearch = (query: string, kbIds: string[]) => {
    runCompare({ query, kb_ids: kbIds, config_a: configA, config_b: configB });
  };

  const idsA = new Set(
    compareResult?.config_a.results.map((r) => r.chunk_id) ?? [],
  );
  const idsB = new Set(
    compareResult?.config_b.results.map((r) => r.chunk_id) ?? [],
  );

  return (
    <div>
      <h1 className="text-xl font-bold text-gray-900">A/B Comparison</h1>
      <p className="text-sm text-gray-500">
        Compare two retrieval configurations side-by-side
      </p>

      <div className="mt-6">
        <QueryInput onSearch={handleSearch} loading={compareLoading} />
      </div>

      {/* Config Panels Side by Side */}
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <ConfigPanel config={configA} onChange={setConfigA} label="Config A (Blue)" />
        <ConfigPanel config={configB} onChange={setConfigB} label="Config B (Purple)" />
      </div>

      {compareLoading && (
        <div className="mt-8 flex justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
        </div>
      )}

      {/* Results */}
      {compareResult && (
        <div className="mt-6 space-y-6">
          {/* Overlap */}
          <OverlapBadge
            shared={compareResult.comparison.shared_chunks}
            onlyA={compareResult.comparison.only_in_a}
            onlyB={compareResult.comparison.only_in_b}
            jaccard={compareResult.comparison.jaccard_similarity}
          />

          {/* Rank changes */}
          {compareResult.comparison.rank_changes.length > 0 && (
            <div className="rounded-lg border border-gray-200 bg-white p-4">
              <h4 className="mb-2 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                Rank Changes (shared chunks)
              </h4>
              <div className="space-y-1">
                {compareResult.comparison.rank_changes.slice(0, 5).map((rc) => (
                  <div
                    key={rc.chunk_id}
                    className="flex items-center gap-2 text-xs"
                  >
                    <span className="font-mono text-gray-400">
                      {rc.chunk_id.slice(0, 8)}
                    </span>
                    <span className="text-blue-600">A:#{rc.rank_a}</span>
                    <span className="text-gray-400">→</span>
                    <span className="text-purple-600">B:#{rc.rank_b}</span>
                    <span
                      className={
                        rc.change > 0
                          ? 'text-green-600'
                          : rc.change < 0
                            ? 'text-red-600'
                            : 'text-gray-400'
                      }
                    >
                      ({rc.change > 0 ? '+' : ''}
                      {rc.change})
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Side-by-side results */}
          <div className="grid gap-4 lg:grid-cols-2">
            {/* Config A */}
            <div>
              <h3 className="mb-2 text-sm font-semibold text-blue-600">
                Config A — {compareResult.config_a.final_count} results
              </h3>
              <TimingBar timings={compareResult.config_a.timings_ms} />
              <div className="mt-3 space-y-3">
                {compareResult.config_a.results.map((r) => (
                  <ResultCard
                    key={r.chunk_id}
                    result={r}
                    highlight={
                      idsB.has(r.chunk_id) ? 'shared' : 'a-only'
                    }
                  />
                ))}
              </div>
            </div>

            {/* Config B */}
            <div>
              <h3 className="mb-2 text-sm font-semibold text-purple-600">
                Config B — {compareResult.config_b.final_count} results
              </h3>
              <TimingBar timings={compareResult.config_b.timings_ms} />
              <div className="mt-3 space-y-3">
                {compareResult.config_b.results.map((r) => (
                  <ResultCard
                    key={r.chunk_id}
                    result={r}
                    highlight={
                      idsA.has(r.chunk_id) ? 'shared' : 'b-only'
                    }
                  />
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
