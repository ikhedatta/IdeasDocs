'use client';

import { useEffect } from 'react';
import { useDataSourceStore } from '@/lib/store';
import { SourceIcon } from '@/components/SourceIcon';
import { SyncStatusBadge } from '@/components/SyncStatusBadge';

export default function ConnectionsPage() {
  const { connectors, connectorsLoading, loadConnectors } = useDataSourceStore();

  useEffect(() => {
    loadConnectors();
  }, []);

  return (
    <div className="p-6 max-w-6xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">My Connections</h2>
          <p className="text-sm text-gray-500 mt-1">
            Manage your active data source connections.
          </p>
        </div>
        <a
          href="/catalog"
          className="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700"
        >
          + Add Source
        </a>
      </div>

      {connectorsLoading ? (
        <div className="text-sm text-gray-400">Loading...</div>
      ) : connectors.length === 0 ? (
        <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
          <p className="text-gray-500 mb-2">No connections yet.</p>
          <p className="text-xs text-gray-400">
            Go to the catalog to connect a data source.
          </p>
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50">
                <th className="text-left px-4 py-3 font-medium text-gray-600">Source</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Name</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Interval</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Updated</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {connectors.map((c) => (
                <tr
                  key={c.id}
                  className="border-b border-gray-50 hover:bg-gray-50 transition-colors"
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <SourceIcon sourceType={c.source_type} size={20} />
                      <span className="text-xs text-gray-500 capitalize">
                        {c.source_type.replace('_', ' ')}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3 font-medium">{c.name}</td>
                  <td className="px-4 py-3">
                    <SyncStatusBadge status={c.status} />
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {c.refresh_interval_minutes}m
                  </td>
                  <td className="px-4 py-3 text-gray-400 text-xs">
                    {new Date(c.updated_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3">
                    <a
                      href={`/connections/${c.id}`}
                      className="text-brand-600 hover:text-brand-700 text-xs font-medium"
                    >
                      View
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
