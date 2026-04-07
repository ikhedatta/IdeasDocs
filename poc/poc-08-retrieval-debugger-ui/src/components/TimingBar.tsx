import type { Timings } from '@/lib/types';
import { Clock } from 'lucide-react';

export function TimingBar({ timings }: { timings: Timings }) {
  const total = timings.total_ms || 1;
  const segments = [
    { label: 'Embed', ms: timings.embed_ms, color: 'bg-blue-400' },
    { label: 'Search', ms: timings.search_ms, color: 'bg-cyan-400' },
    { label: 'Rerank', ms: timings.rerank_ms, color: 'bg-purple-400' },
  ];

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-3">
      <div className="mb-2 flex items-center gap-1.5 text-xs text-gray-500">
        <Clock className="h-3.5 w-3.5" />
        Total: {total}ms
      </div>

      {/* Stacked bar */}
      <div className="flex h-4 overflow-hidden rounded-full bg-gray-100">
        {segments.map((seg) => (
          <div
            key={seg.label}
            className={`${seg.color} transition-all`}
            style={{ width: `${(seg.ms / total) * 100}%` }}
            title={`${seg.label}: ${seg.ms}ms`}
          />
        ))}
      </div>

      {/* Legend */}
      <div className="mt-2 flex gap-4">
        {segments.map((seg) => (
          <span key={seg.label} className="flex items-center gap-1 text-[11px] text-gray-500">
            <span className={`inline-block h-2 w-2 rounded-full ${seg.color}`} />
            {seg.label}: {seg.ms}ms
          </span>
        ))}
      </div>
    </div>
  );
}
