'use client';

import { useState } from 'react';
import type { RetrievalConfig } from '@/lib/types';

interface ConfigPanelProps {
  config: Partial<RetrievalConfig>;
  onChange: (config: Partial<RetrievalConfig>) => void;
  label?: string;
}

export function ConfigPanel({ config, onChange, label }: ConfigPanelProps) {
  const update = (key: string, value: number | string | null) =>
    onChange({ ...config, [key]: value });

  const denseWeight = config.dense_weight ?? 0.7;
  const sparseWeight = config.sparse_weight ?? 0.3;

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      {label && (
        <h3 className="mb-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
          {label}
        </h3>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        {/* Top K */}
        <div>
          <label className="text-xs text-gray-500">Top K</label>
          <input
            type="number"
            min={1}
            max={100}
            value={config.top_k ?? 20}
            onChange={(e) => update('top_k', Number(e.target.value))}
            className="mt-1 w-full rounded border border-gray-200 px-2 py-1.5 text-sm focus:border-blue-300 focus:outline-none"
          />
        </div>

        {/* Final K */}
        <div>
          <label className="text-xs text-gray-500">Final K</label>
          <input
            type="number"
            min={1}
            max={50}
            value={config.final_k ?? 10}
            onChange={(e) => update('final_k', Number(e.target.value))}
            className="mt-1 w-full rounded border border-gray-200 px-2 py-1.5 text-sm focus:border-blue-300 focus:outline-none"
          />
        </div>

        {/* Dense Weight */}
        <div className="sm:col-span-2">
          <div className="flex items-center justify-between">
            <label className="text-xs text-gray-500">
              Dense: {denseWeight.toFixed(2)}
            </label>
            <label className="text-xs text-gray-500">
              Sparse: {sparseWeight.toFixed(2)}
            </label>
          </div>
          <input
            type="range"
            min={0}
            max={100}
            value={denseWeight * 100}
            onChange={(e) => {
              const d = Number(e.target.value) / 100;
              onChange({
                ...config,
                dense_weight: Number(d.toFixed(2)),
                sparse_weight: Number((1 - d).toFixed(2)),
              });
            }}
            className="mt-1 w-full accent-blue-600"
          />
          <div className="mt-0.5 flex justify-between text-[10px] text-gray-400">
            <span>Semantic</span>
            <span>Keyword</span>
          </div>
        </div>

        {/* Threshold */}
        <div>
          <label className="text-xs text-gray-500">Threshold</label>
          <input
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={config.similarity_threshold ?? 0}
            onChange={(e) => update('similarity_threshold', Number(e.target.value))}
            className="mt-1 w-full rounded border border-gray-200 px-2 py-1.5 text-sm focus:border-blue-300 focus:outline-none"
          />
        </div>

        {/* Rerank Model */}
        <div>
          <label className="text-xs text-gray-500">Rerank Model</label>
          <select
            value={config.rerank_model ?? ''}
            onChange={(e) => update('rerank_model', e.target.value || null)}
            className="mt-1 w-full rounded border border-gray-200 px-2 py-1.5 text-sm focus:border-blue-300 focus:outline-none"
          >
            <option value="">None</option>
            <option value="rerank-english-v3.0">Cohere rerank-english-v3.0</option>
            <option value="rerank-multilingual-v3.0">Cohere rerank-multilingual-v3.0</option>
            <option value="jina-reranker-v2-base-multilingual">Jina reranker-v2</option>
          </select>
        </div>
      </div>
    </div>
  );
}
