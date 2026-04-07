import type { SourceInfo } from '@/lib/types';
import { SourceIcon } from './SourceIcon';
import { CATEGORIES } from '@/lib/types';

interface ConnectorCardProps {
  source: SourceInfo;
}

export function ConnectorCard({ source }: ConnectorCardProps) {
  const cat = CATEGORIES[source.category];

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5 hover:border-brand-300 hover:shadow-sm transition-all">
      <div className="flex items-start gap-3 mb-3">
        <SourceIcon sourceType={source.source_type} size={32} />
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-sm">{source.display_name}</h3>
          {cat && (
            <span className={`inline-block mt-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${cat.color}`}>
              {cat.label}
            </span>
          )}
        </div>
      </div>

      <p className="text-xs text-gray-500 mb-4 line-clamp-2">{source.description}</p>

      <div className="flex items-center justify-between">
        <div className="flex gap-1">
          {source.auth_methods.map((m) => (
            <span key={m} className="px-1.5 py-0.5 bg-gray-100 rounded text-[10px] text-gray-500">
              {m.replace('_', ' ')}
            </span>
          ))}
        </div>
        <a
          href={`/connect/${source.source_type}`}
          className="px-3 py-1.5 bg-brand-600 text-white text-xs rounded-lg hover:bg-brand-700"
        >
          Connect
        </a>
      </div>
    </div>
  );
}
