'use client';

import { useState } from 'react';
import { useDebugStore } from '@/store/useDebugStore';
import { ConfigPanel } from '@/components/ConfigPanel';
import { BatchResults } from '@/components/BatchResults';
import type { RetrievalConfig, TestCase } from '@/lib/types';
import { Loader2, Play, Upload } from 'lucide-react';

const EXAMPLE_SUITE: TestCase[] = [
  { query: 'What is the fire safety evacuation procedure?', expected_keywords: ['fire', 'evacuation', 'safety'] },
  { query: 'How many vacation days do employees get?', expected_keywords: ['vacation', 'PTO', 'days'] },
  { query: 'What is the remote work policy?', expected_keywords: ['remote', 'work', 'home'] },
];

export default function BatchPage() {
  const [kbIds, setKbIds] = useState('');
  const [suiteJson, setSuiteJson] = useState(
    JSON.stringify(EXAMPLE_SUITE, null, 2),
  );
  const [config, setConfig] = useState<Partial<RetrievalConfig>>({
    top_k: 20,
    final_k: 10,
    dense_weight: 0.7,
    sparse_weight: 0.3,
  });

  const { batchResult, batchLoading, runBatch } = useDebugStore();

  const handleRun = () => {
    if (!kbIds.trim()) return;
    let testCases: TestCase[];
    try {
      testCases = JSON.parse(suiteJson);
    } catch {
      alert('Invalid JSON in test suite');
      return;
    }
    runBatch({
      kb_ids: kbIds.split(',').map((s) => s.trim()).filter(Boolean),
      test_cases: testCases,
      config,
    });
  };

  return (
    <div>
      <h1 className="text-xl font-bold text-gray-900">Batch Test Suite</h1>
      <p className="text-sm text-gray-500">
        Run multiple test queries and compute Recall@K and keyword hit rate
      </p>

      <div className="mt-6 space-y-4">
        {/* KB IDs */}
        <div>
          <label className="text-xs font-medium text-gray-500">
            Knowledge Base IDs (comma-separated)
          </label>
          <input
            type="text"
            value={kbIds}
            onChange={(e) => setKbIds(e.target.value)}
            placeholder="my-kb, other-kb"
            className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-blue-300 focus:outline-none"
          />
        </div>

        {/* Config */}
        <ConfigPanel config={config} onChange={setConfig} label="Retrieval Config" />

        {/* Test Suite JSON */}
        <div>
          <div className="flex items-center justify-between">
            <label className="text-xs font-medium text-gray-500">
              Test Suite (JSON)
            </label>
            <button
              onClick={() => setSuiteJson(JSON.stringify(EXAMPLE_SUITE, null, 2))}
              className="text-xs text-blue-600 hover:underline"
            >
              Load Example
            </button>
          </div>
          <textarea
            value={suiteJson}
            onChange={(e) => setSuiteJson(e.target.value)}
            rows={10}
            spellCheck={false}
            className="mt-1 w-full rounded-lg border border-gray-200 p-3 font-mono text-xs text-gray-800 focus:border-blue-300 focus:outline-none"
          />
          <p className="mt-1 text-[11px] text-gray-400">
            Each test case: {`{ "query": "...", "expected_chunk_ids": [...], "expected_keywords": [...] }`}
          </p>
        </div>

        {/* Run button */}
        <button
          onClick={handleRun}
          disabled={batchLoading || !kbIds.trim()}
          className="flex items-center gap-1.5 rounded-lg bg-purple-600 px-6 py-2 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50"
        >
          {batchLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Play className="h-4 w-4" />
          )}
          {batchLoading ? 'Running...' : 'Run Test Suite'}
        </button>
      </div>

      {/* Results */}
      {batchResult && (
        <div className="mt-8">
          <BatchResults
            summary={batchResult.summary}
            results={batchResult.test_results}
          />
        </div>
      )}
    </div>
  );
}
