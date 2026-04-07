'use client';

import { Search } from 'lucide-react';
import { useState } from 'react';

interface QueryInputProps {
  onSearch: (query: string, kbIds: string[]) => void;
  loading: boolean;
}

export function QueryInput({ onSearch, loading }: QueryInputProps) {
  const [query, setQuery] = useState('');
  const [kbIds, setKbIds] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || !kbIds.trim()) return;
    onSearch(
      query.trim(),
      kbIds.split(',').map((s) => s.trim()).filter(Boolean),
    );
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Enter your search query..."
          className="w-full rounded-lg border border-gray-200 bg-white py-3 pl-10 pr-4 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-300 focus:outline-none focus:ring-1 focus:ring-blue-300"
        />
      </div>
      <div className="flex gap-3">
        <input
          type="text"
          value={kbIds}
          onChange={(e) => setKbIds(e.target.value)}
          placeholder="KB IDs (comma-separated)"
          className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-blue-300 focus:outline-none"
        />
        <button
          type="submit"
          disabled={loading || !query.trim() || !kbIds.trim()}
          className="rounded-lg bg-blue-600 px-6 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? 'Searching...' : 'Search'}
        </button>
      </div>
    </form>
  );
}
