import type { SyncLog } from '@/lib/types';
import { SyncStatusBadge } from './SyncStatusBadge';

interface SyncTimelineProps {
  logs: SyncLog[];
}

export function SyncTimeline({ logs }: SyncTimelineProps) {
  if (logs.length === 0) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-6 text-center text-gray-400 text-sm">
        No sync logs yet. Trigger a sync to see activity here.
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100 bg-gray-50">
            <th className="text-left px-4 py-2 font-medium text-gray-600">Status</th>
            <th className="text-left px-4 py-2 font-medium text-gray-600">Started</th>
            <th className="text-left px-4 py-2 font-medium text-gray-600">Duration</th>
            <th className="text-right px-4 py-2 font-medium text-gray-600">Fetched</th>
            <th className="text-right px-4 py-2 font-medium text-gray-600">New</th>
            <th className="text-right px-4 py-2 font-medium text-gray-600">Updated</th>
            <th className="text-right px-4 py-2 font-medium text-gray-600">Failed</th>
            <th className="text-left px-4 py-2 font-medium text-gray-600">Error</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((log) => {
            const duration = getDuration(log);
            return (
              <tr key={log.id} className="border-b border-gray-50 hover:bg-gray-50">
                <td className="px-4 py-2">
                  <SyncStatusBadge status={log.status} />
                </td>
                <td className="px-4 py-2 text-gray-500 text-xs">
                  {log.started_at ? new Date(log.started_at).toLocaleString() : '—'}
                </td>
                <td className="px-4 py-2 text-gray-500 text-xs font-mono">{duration}</td>
                <td className="px-4 py-2 text-right font-mono">{log.docs_fetched}</td>
                <td className="px-4 py-2 text-right font-mono text-green-600">{log.docs_new}</td>
                <td className="px-4 py-2 text-right font-mono text-blue-600">{log.docs_updated}</td>
                <td className="px-4 py-2 text-right font-mono text-red-600">{log.docs_failed}</td>
                <td className="px-4 py-2 text-xs text-red-500 truncate max-w-[200px]">
                  {log.error_message || '—'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function getDuration(log: SyncLog): string {
  if (!log.started_at || !log.finished_at) return '—';
  const ms = new Date(log.finished_at).getTime() - new Date(log.started_at).getTime();
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}
