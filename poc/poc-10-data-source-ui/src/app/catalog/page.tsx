'use client';

import { useEffect, useState } from 'react';
import { useDataSourceStore } from '@/lib/store';
import { ConnectorCard } from '@/components/ConnectorCard';
import { CATEGORIES } from '@/lib/types';

export default function CatalogPage() {
  const { sources, sourcesLoading, loadSources } = useDataSourceStore();
  const [filter, setFilter] = useState<string>('all');

  useEffect(() => {
    loadSources();
  }, []);

  const categories = ['all', ...new Set(sources.map((s) => s.category))];
  const filtered =
    filter === 'all' ? sources : sources.filter((s) => s.category === filter);

  return (
    <div className="p-6 max-w-6xl">
      <h2 className="text-2xl font-bold mb-1">Source Catalog</h2>
      <p className="text-sm text-gray-500 mb-6">
        Browse available data sources and connect them to your knowledge bases.
      </p>

      {/* Category filter */}
      <div className="flex gap-2 mb-6 flex-wrap">
        {categories.map((cat) => {
          const meta = CATEGORIES[cat];
          return (
            <button
              key={cat}
              onClick={() => setFilter(cat)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                filter === cat
                  ? 'bg-brand-600 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {cat === 'all' ? 'All' : meta?.label || cat}
            </button>
          );
        })}
      </div>

      {sourcesLoading ? (
        <div className="text-sm text-gray-400">Loading sources...</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((source) => (
            <ConnectorCard key={source.source_type} source={source} />
          ))}
        </div>
      )}
    </div>
  );
}
