import type { KBStats } from '@/lib/types';
import { FileText, Layers, ToggleLeft, Hash } from 'lucide-react';

export function StatsBar({ stats }: { stats: KBStats }) {
  const items = [
    { icon: FileText, label: 'Documents', value: stats.document_count },
    { icon: Layers, label: 'Chunks', value: stats.chunk_count },
    { icon: ToggleLeft, label: 'Active', value: stats.active_chunks },
    { icon: Hash, label: 'Est. Tokens', value: stats.estimated_tokens.toLocaleString() },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {items.map((item) => (
        <div
          key={item.label}
          className="flex items-center gap-3 rounded-lg border border-gray-200 bg-white px-4 py-3"
        >
          <item.icon className="h-5 w-5 text-gray-400" />
          <div>
            <p className="text-lg font-semibold text-gray-900">{item.value}</p>
            <p className="text-xs text-gray-500">{item.label}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
