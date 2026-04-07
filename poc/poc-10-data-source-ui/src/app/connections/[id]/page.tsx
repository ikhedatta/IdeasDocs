'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { useDataSourceStore } from '@/lib/store';
import { SourceIcon } from '@/components/SourceIcon';
import { SyncStatusBadge } from '@/components/SyncStatusBadge';
import { SyncTimeline } from '@/components/SyncTimeline';
import { ContentBrowser } from '@/components/ContentBrowser';

export default function ConnectionDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const [tab, setTab] = useState<'overview' | 'logs' | 'browse'>('overview');

  const {
    activeConnector,
    activeLoading,
    loadConnector,
    syncLogs,
    loadSyncLogs,
    triggerSync,
    cancelSync,
    deleteConnector,
    validateConnector,
  } = useDataSourceStore();

  useEffect(() => {
    loadConnector(id);
    loadSyncLogs(id);
  }, [id]);

  const conn = activeConnector?.connector;
  const info = activeConnector?.source_info;
  const lastSync = activeConnector?.last_sync;

  if (activeLoading) {
    return <div className="p-6 text-gray-400">Loading...</div>;
  }
  if (!conn) {
    return <div className="p-6 text-red-500">Connector not found.</div>;
  }

  return (
    <div className="p-6 max-w-5xl">
      {/* Header */}
      <div className="flex items-start gap-4 mb-6">
        <SourceIcon sourceType={conn.source_type} size={48} />
        <div className="flex-1">
          <h2 className="text-2xl font-bold">{conn.name}</h2>
          <p className="text-sm text-gray-500">{info?.description}</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => triggerSync(id)}
            className="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700"
          >
            Sync Now
          </button>
          <button
            onClick={() => triggerSync(id, true)}
            className="px-4 py-2 bg-gray-100 text-gray-700 text-sm rounded-lg hover:bg-gray-200"
          >
            Full Reindex
          </button>
          <button
            onClick={async () => {
              const result = await validateConnector(id);
              alert(result.valid ? 'Connection valid!' : `Invalid: ${result.error}`);
            }}
            className="px-4 py-2 bg-gray-100 text-gray-700 text-sm rounded-lg hover:bg-gray-200"
          >
            Test
          </button>
        </div>
      </div>

      {/* Info cards */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <InfoCard label="Status" value={<SyncStatusBadge status={conn.status} />} />
        <InfoCard label="Auth" value={conn.auth_method.replace('_', ' ')} />
        <InfoCard label="Interval" value={`${conn.refresh_interval_minutes} min`} />
        <InfoCard
          label="Last Sync"
          value={
            lastSync?.finished_at
              ? new Date(lastSync.finished_at).toLocaleString()
              : 'Never'
          }
        />
      </div>

      {/* Last sync stats */}
      {lastSync && (
        <div className="grid grid-cols-4 gap-4 mb-6">
          <InfoCard label="Docs Fetched" value={lastSync.docs_fetched} />
          <InfoCard label="New" value={lastSync.docs_new} />
          <InfoCard label="Updated" value={lastSync.docs_updated} />
          <InfoCard label="Failed" value={lastSync.docs_failed} />
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-gray-200 mb-4">
        <div className="flex gap-6">
          {(['overview', 'logs', 'browse'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`pb-2 text-sm font-medium border-b-2 transition-colors ${
                tab === t
                  ? 'border-brand-600 text-brand-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      {tab === 'overview' && (
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h3 className="font-medium mb-3">Configuration</h3>
          <div className="grid grid-cols-2 gap-2 text-sm">
            {Object.entries(conn.config).map(([k, v]) => (
              <div key={k} className="flex gap-2">
                <span className="text-gray-500 font-mono text-xs">{k}:</span>
                <span className="text-gray-900 text-xs">{JSON.stringify(v)}</span>
              </div>
            ))}
          </div>
          <h3 className="font-medium mt-4 mb-3">Credentials (masked)</h3>
          <div className="grid grid-cols-2 gap-2 text-sm">
            {Object.entries(conn.credentials).map(([k, v]) => (
              <div key={k} className="flex gap-2">
                <span className="text-gray-500 font-mono text-xs">{k}:</span>
                <span className="text-gray-900 text-xs font-mono">{v}</span>
              </div>
            ))}
          </div>

          <div className="mt-6 pt-4 border-t border-gray-200 flex justify-end">
            <button
              onClick={async () => {
                if (confirm('Delete this connection?')) {
                  await deleteConnector(id);
                  window.location.href = '/connections';
                }
              }}
              className="px-4 py-2 bg-red-50 text-red-600 text-sm rounded-lg hover:bg-red-100"
            >
              Delete Connection
            </button>
          </div>
        </div>
      )}

      {tab === 'logs' && <SyncTimeline logs={syncLogs} />}

      {tab === 'browse' && <ContentBrowser connectorId={id} />}
    </div>
  );
}

function InfoCard({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 px-4 py-3">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className="text-sm font-medium">{typeof value === 'number' ? value : value}</div>
    </div>
  );
}
