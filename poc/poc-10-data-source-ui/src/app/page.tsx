'use client';

import { useEffect } from 'react';
import { useDataSourceStore } from '@/lib/store';
import { SyncStatusBadge } from '@/components/SyncStatusBadge';
import { SourceIcon } from '@/components/SourceIcon';

export default function DashboardPage() {
  const { connectors, connectorsLoading, loadConnectors, sources, loadSources } =
    useDataSourceStore();

  useEffect(() => {
    loadSources();
    loadConnectors();
  }, []);

  const activeCount = connectors.filter((c) => c.status === 'active').length;
  const errorCount = connectors.filter((c) => c.status === 'error').length;

  return (
    <div className="p-6 max-w-6xl">
      <h2 className="text-2xl font-bold mb-1">Dashboard</h2>
      <p className="text-sm text-gray-500 mb-6">
        Overview of connected data sources and sync activity.
      </p>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <StatCard label="Available Sources" value={sources.length} color="blue" />
        <StatCard label="Connected" value={connectors.length} color="green" />
        <StatCard label="Active" value={activeCount} color="emerald" />
        <StatCard label="Errors" value={errorCount} color="red" />
      </div>

      {/* Connected sources */}
      <h3 className="text-lg font-semibold mb-3">Connected Sources</h3>

      {connectorsLoading ? (
        <div className="text-sm text-gray-400">Loading...</div>
      ) : connectors.length === 0 ? (
        <div className="bg-white rounded-lg border border-gray-200 p-8 text-center">
          <p className="text-gray-500 mb-3">No data sources connected yet.</p>
          <a
            href="/catalog"
            className="inline-block px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700"
          >
            Browse Catalog
          </a>
        </div>
      ) : (
        <div className="space-y-2">
          {connectors.map((c) => (
            <a
              key={c.id}
              href={`/connections/${c.id}`}
              className="flex items-center gap-4 bg-white rounded-lg border border-gray-200 p-4 hover:border-brand-300 transition-colors"
            >
              <SourceIcon sourceType={c.source_type} size={32} />
              <div className="flex-1 min-w-0">
                <div className="font-medium text-sm truncate">{c.name}</div>
                <div className="text-xs text-gray-500">{c.source_type}</div>
              </div>
              <SyncStatusBadge status={c.status} />
              <div className="text-xs text-gray-400">
                {new Date(c.updated_at).toLocaleDateString()}
              </div>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  const bg = `bg-${color}-50`;
  const text = `text-${color}-700`;
  return (
    <div className={`rounded-lg border border-gray-200 p-4 ${bg}`}>
      <div className={`text-2xl font-bold ${text}`}>{value}</div>
      <div className="text-xs text-gray-600 mt-1">{label}</div>
    </div>
  );
}
